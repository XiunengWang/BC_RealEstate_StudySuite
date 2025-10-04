from __future__ import annotations
import time
import streamlit as st
from supabase import AuthApiError
from supabase_client import get_supabase


# ----------------------------- Helpers -----------------------------
def _rerun():
    if hasattr(st, "rerun"):
        st.rerun()
    elif hasattr(st, "experimental_rerun"):
        st.experimental_rerun()


def _apply_session_to_client():
    """Attach stored auth session to the Supabase client so RLS-protected queries work."""
    sess = st.session_state.get("sb_session")
    if not sess:
        return
    sb = get_supabase()
    try:
        access = sess.get("access_token")
        refresh = sess.get("refresh_token")
        if access and refresh:
            sb.auth.set_session(access_token=access, refresh_token=refresh)
    except Exception:
        pass


# ----------------------------- Auth UI -----------------------------
def auth_ui():
    """
    Renders login/signup in the sidebar, persists session in st.session_state,
    and returns the current user dict when authenticated.
    Shows a clear error if Supabase config is missing.
    """
    if "sb_session" not in st.session_state:
        st.session_state.sb_session = None

    # Guard get_supabase so we can show a friendly error instead of blank page
    try:
        supabase = get_supabase()
    except Exception as e:
        with st.sidebar:
            st.header("Account")
            st.error(
                "Supabase is not configured. Set **SUPABASE_URL** and **SUPABASE_ANON_KEY** "
                "in `.env` (local) or in Streamlit **Secrets** (cloud)."
            )
            st.caption(f"Details: {e}")
        return None

    # Refresh token if near expiry
    sess = st.session_state.sb_session
    if sess and sess.get("expires_at") and time.time() > (sess["expires_at"] - 60):
        try:
            refreshed = supabase.auth.refresh_session()
            if refreshed and refreshed.session:
                st.session_state.sb_session = refreshed.session.model_dump()
        except Exception:
            pass

    # Already authenticated
    if st.session_state.sb_session and st.session_state.sb_session.get("user"):
        _apply_session_to_client()
        user = st.session_state.sb_session["user"]
        with st.sidebar:
            st.success(f"Signed in as {user.get('email')}")
            if st.button("Log out"):
                try:
                    supabase.auth.sign_out()
                except Exception:
                    pass
                st.session_state.sb_session = None
                # ensure next login reloads from server before saving
                for k in ("progress_loaded", "progress_baseline"):
                    st.session_state.pop(k, None)
                _rerun()
        return user

    # Not authenticated → login/signup UI
    with st.sidebar:
        st.header("Account")
        tab_login, tab_signup = st.tabs(["Log in", "Sign up"])

        with tab_login:
            email = st.text_input("Email", key="login_email")
            password = st.text_input("Password", type="password", key="login_pw")
            if st.button("Log in"):
                try:
                    resp = supabase.auth.sign_in_with_password(
                        {"email": email, "password": password}
                    )
                    if resp and resp.session:
                        st.session_state.sb_session = resp.session.model_dump()
                        _apply_session_to_client()
                        _rerun()
                    else:
                        st.error(
                            "No session returned from Supabase. Check project URL/key."
                        )
                except AuthApiError as e:
                    st.error(f"Login failed: {e}")
                except Exception as e:
                    st.error(f"Login error: {e}")

        with tab_signup:
            email_s = st.text_input("Email", key="signup_email")
            password_s = st.text_input("Password", type="password", key="signup_pw")
            if st.button("Create account"):
                try:
                    resp = supabase.auth.sign_up(
                        {"email": email_s, "password": password_s}
                    )
                    if getattr(resp, "user", None):
                        st.success(
                            "Account created. Check email if confirmation is required, then log in."
                        )
                    else:
                        st.info(
                            "If email confirmation is required, verify and then log in."
                        )
                except AuthApiError as e:
                    st.error(f"Signup failed: {e}")
                except Exception as e:
                    st.error(f"Signup error: {e}")
    return None


def current_user_id() -> str | None:
    sess = st.session_state.get("sb_session")
    if not sess:
        return None
    user = sess.get("user")
    return user.get("id") if user else None


# ------------------------ Progress Load/Save ------------------------
DEFAULT_PROGRESS = {
    "attempts": 0,
    "correct": 0,
    "wrong_ids": [],
    "seen_ids": [],
}


def _normalize_progress(p: dict | None) -> dict:
    if not p:
        return DEFAULT_PROGRESS.copy()
    out = DEFAULT_PROGRESS.copy()
    out["attempts"] = int((p.get("attempts") or 0))
    out["correct"] = int((p.get("correct") or 0))
    wi = p.get("wrong_ids") or []
    si = p.get("seen_ids") or []
    out["wrong_ids"] = list(wi) if isinstance(wi, list) else list(wi)
    out["seen_ids"] = list(si) if isinstance(si, list) else list(si)
    return out


def _fetch_server_progress(sb, uid: str) -> dict:
    resp = sb.table("progress").select("*").eq("user_id", uid).limit(1).execute()
    data = (
        getattr(resp, "data", None) if not isinstance(resp, dict) else resp.get("data")
    )
    row = data[0] if isinstance(data, list) and data else None
    return _normalize_progress(row)


def load_progress() -> dict:
    uid = current_user_id()
    if not uid:
        raise RuntimeError("User not authenticated.")

    _apply_session_to_client()
    sb = get_supabase()

    try:
        server_p = _fetch_server_progress(sb, uid)
    except Exception:
        server_p = DEFAULT_PROGRESS.copy()

    # Store a baseline snapshot for delta merges later (multi-device safety)
    st.session_state.progress_baseline = server_p.copy()
    return server_p


def save_progress(p: dict) -> None:
    """
    Merge-save to Supabase:
      - Read server's current row
      - Compute local deltas since baseline
      - Add deltas to server counters
      - Merge sets:
          seen_ids = union(server, local)
          wrong_ids = union(server, local) - (locally corrected set)
    """
    # Ensure we loaded once this session
    if not st.session_state.get("progress_loaded", False):
        try:
            loaded = load_progress()
            st.session_state.progress = loaded
            st.session_state.progress_loaded = True
        except Exception:
            st.warning("Skipping save: progress not loaded yet.")
            return

    uid = current_user_id()
    if not uid:
        raise RuntimeError("User not authenticated.")

    _apply_session_to_client()
    sb = get_supabase()

    # 1) Get server and baseline
    try:
        server = _fetch_server_progress(sb, uid)
    except Exception as e:
        st.warning(
            f"Could not read server progress; falling back to simple upsert. ({e})"
        )
        server = DEFAULT_PROGRESS.copy()

    baseline = st.session_state.get("progress_baseline") or server.copy()

    # 2) Compute deltas vs baseline (avoid double counting across devices)
    local_attempts = int(p.get("attempts", 0))
    local_correct = int(p.get("correct", 0))
    base_attempts = int(baseline.get("attempts", 0))
    base_correct = int(baseline.get("correct", 0))

    d_attempts = max(0, local_attempts - base_attempts)
    d_correct = max(0, local_correct - base_correct)

    # 3) Merge counters with server
    merged_attempts = int(server.get("attempts", 0)) + d_attempts
    merged_correct = int(server.get("correct", 0)) + d_correct

    # 4) Merge sets
    local_seen = set(p.get("seen_ids", []) or [])
    local_wrong = set(p.get("wrong_ids", []) or [])
    server_seen = set(server.get("seen_ids", []) or [])
    server_wrong = set(server.get("wrong_ids", []) or [])

    merged_seen = sorted(server_seen | local_seen)

    # Treat "seen but not wrong locally" as corrected locally → remove from merged wrong
    locally_corrected_ids = local_seen - local_wrong
    merged_wrong = (server_wrong | local_wrong) - locally_corrected_ids
    merged_wrong = sorted(merged_wrong)

    payload = {
        "user_id": uid,
        "attempts": merged_attempts,
        "correct": merged_correct,
        "wrong_ids": merged_wrong,
        "seen_ids": merged_seen,
        "updated_at": "now()",
    }

    # 5) Save and update the baseline to the merged view (so future deltas are from this point)
    try:
        sb.table("progress").upsert(payload).execute()
        st.session_state.progress_baseline = {
            "attempts": merged_attempts,
            "correct": merged_correct,
            "wrong_ids": merged_wrong,
            "seen_ids": merged_seen,
        }
    except Exception as e:
        st.warning(f"Progress save failed: {e}")
