
import sys, runpy, os
import streamlit as st
from pathlib import Path

def _noop(*args, **kwargs):
    return None

def _patch_set_page_config():
    if not hasattr(st, "_ssuite_patched"):
        st._ssuite_patched = True
        try:
            st.set_page_config = _noop  # type: ignore
        except Exception:
            pass

def _patch_safe_secrets():
    # If no secrets.toml exists, let st.secrets read from env to avoid StreamlitSecretNotFoundError
    default_paths = [
        Path.home() / ".streamlit" / "secrets.toml",
        Path.cwd() / ".streamlit" / "secrets.toml",
    ]
    if any(p.exists() for p in default_paths):
        return
    class EnvSecrets(dict):
        def get(self, key, default=None):  # type: ignore[override]
            return os.environ.get(key, default)
    try:
        st.secrets = EnvSecrets(os.environ.copy())  # type: ignore[attr-defined]
    except Exception:
        pass

def ensure_path(path):
    path = str(path)
    if path not in sys.path:
        sys.path.insert(0, path)

def require_login():
    sess = st.session_state.get("sb_session")
    if not (sess and sess.get("user")):
        st.info("Please sign in from the Home page to use this feature.")
        return False
    return True

def run_mcq_app(mcq_dir):
    mcq_dir = Path(mcq_dir)
    ensure_path(mcq_dir.as_posix())
    import importlib
    ap = importlib.import_module("auth_and_progress")
    original_auth_ui = getattr(ap, "auth_ui", None)
    def unified_auth_ui():
        sess = st.session_state.get("sb_session")
        if sess and sess.get("user"):
            return sess["user"]
        with st.sidebar:
            st.info("Sign in on the Home page to access MCQs.")
        return None
    ap.auth_ui = unified_auth_ui  # type: ignore
    _patch_set_page_config()
    _patch_safe_secrets()
    app_py = mcq_dir / "app.py"
    # sanitize foreign 'mode' for safety
    try:
        valid = {"All","Range","Random N","Wrong only","Not done yet","Calculation only","Non-calculation only"}
        if st.session_state.get("mode") not in valid:
            st.session_state.pop("mode", None)
    except Exception:
        pass
    runpy.run_path(str(app_py), init_globals={"__name__": "__main__"})
    if original_auth_ui is not None:
        ap.auth_ui = original_auth_ui  # type: ignore

def run_flashcards_app(flash_dir):
    flash_dir = Path(flash_dir)
    ensure_path(flash_dir.as_posix())
    _patch_set_page_config()
    _patch_safe_secrets()
    script = flash_dir / "streamlit_app.py"
    runpy.run_path(str(script), init_globals={"__name__": "__main__"})

def run_mindmap_app(mind_dir):
    mind_dir = Path(mind_dir)
    ensure_path(mind_dir.as_posix())
    _patch_set_page_config()
    _patch_safe_secrets()
    script = mind_dir / "app_simple.py"
    runpy.run_path(str(script), init_globals={"__name__": "__main__"})
