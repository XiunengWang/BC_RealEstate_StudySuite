from __future__ import annotations

from pathlib import Path
import json
import random
import re
import streamlit as st

# ---------- Page setup ----------
st.set_page_config(page_title="Flashcards", layout="wide")

# Where your existing data lives: modules/FlashCards/data/ch_*.json
MODULE_DATA_DIR = Path(__file__).parents[1] / "modules" / "FlashCards" / "data"

# ---------- Styles (dark, Quizlet-ish) ----------
st.markdown(
    """
<style>
.main, .block-container { background-color: #0b0b0b !important; }
:root { --card-bg:#111; --card-fg:#f4f4f4; --muted:#9aa0a6; --accent:#3b82f6; }

.page-title { color:#fff; margin-bottom: .25rem; }

.toolbar { display:flex; gap:.75rem; align-items:center; justify-content:center; margin:.25rem 0 .25rem; }
.toolbar button { background:#1b1b1b; color:#e5e5e5; border:1px solid #2a2a2a; padding:.55rem .9rem; border-radius:10px; }
.toolbar button:hover { background:#222; }

.card-wrap { display:flex; justify-content:center; }
.card {
  width: min(1100px, 92vw);
  min-height: 360px;
  background: var(--card-bg);
  color: var(--card-fg);
  border-radius: 18px;
  box-shadow: 0 30px 80px rgba(0,0,0,.35);
  margin: .9rem auto .35rem;
  padding: clamp(28px, 4vw, 56px);
  position: relative;
}
.card .hint { position:absolute; top: 12px; left: 18px; color: var(--muted); font-size: .85rem; }
.card .progress { position:absolute; bottom: 12px; left: 18px; color: var(--muted); font-size: .85rem; }
.card .chapter { position:absolute; top: 12px; right: 18px; color: #cbd5e1; font-size: .85rem; }
.card .center {
  display: block;             /* was flex; flex caused odd wrapping */
  text-align: center;
  min-height: 260px;
  font-size: clamp(22px, 2.2vw, 36px);
  line-height: 1.45;
  white-space: normal;
  word-break: normal;
}
/* Make <strong> (and <b>) render as "Green Strong" */
.card .center strong,
.card .center b {
  color: #22c55e;             /* green-500 */
  font-weight: 800;
}
.navbar { display:flex; justify-content:center; align-items:center; gap:.6rem; margin-top:.2rem; }
.navbar button {
  background:#141414; border:1px solid #2a2a2a; color:#ddd;
  padding:.55rem .9rem; border-radius:10px; cursor:pointer;
}
.navbar button:hover { background:#1a1a1a; }

.stMultiSelect [data-baseweb="tag"] { background:#1f1f1f; color:#ddd; }



</style>
""",
    unsafe_allow_html=True,
)

st.markdown('<h1 class="page-title">Flashcards</h1>', unsafe_allow_html=True)


# ---------- Data loading ----------
@st.cache_data(show_spinner=False)
def load_cards_from_module() -> list[dict]:
    """Read all ch_*.json in modules/FlashCards/data and return normalized cards."""
    cards: list[dict] = []
    if not MODULE_DATA_DIR.exists():
        return cards
    for jf in sorted(MODULE_DATA_DIR.glob("*.json")):
        try:
            data = json.loads(jf.read_text(encoding="utf-8"))
        except Exception:
            continue
        chapter = infer_chapter_name(jf.stem)  # e.g., ch_00 -> "Chapter 00"
        for row in data:
            q_raw = row.get("question", "")
            a_raw = row.get("answer", "")
            q = normalize_html(q_raw)
            a = normalize_html(a_raw)
            if q or a:
                cards.append(
                    {
                        "chapter": chapter,
                        "front_html": q,  # keep your HTML
                        "back_html": a,  # keep your HTML
                    }
                )
    return cards


def infer_chapter_name(stem: str) -> str:
    m = re.search(r"(\d+)", stem)
    if m:
        return f"Chapter {m.group(1).zfill(2)}"
    return stem.replace("_", " ").title()


def normalize_html(s: str) -> str:
    if not isinstance(s, str):
        return ""
    s = (
        s.replace("&nbsp;", " ")
        .replace("<br />", "<br>")
        .replace("<br/>", "<br>")
        .strip()
    )
    # Insert a space when a letter/number touches <strong> boundaries
    s = re.sub(r"([A-Za-z0-9])<\s*strong\b", r"\1 <strong", s)
    s = re.sub(r"</\s*strong>([A-Za-z0-9])", r"</strong> \1", s)

    # Collapse <br> inside <strong>…</strong> to spaces so multi-word bold stays inline
    def _fix_strong(m: re.Match) -> str:
        inner = re.sub(r"<br\s*/?>", " ", m.group(1))
        inner = re.sub(r"\s+", " ", inner).strip()
        return f"<strong>{inner}</strong>"

    s = re.sub(r"<strong[^>]*>(.*?)</strong>", _fix_strong, s, flags=re.I | re.S)
    return s


def back_html_for(card: dict) -> str:
    """
    Make the back clearer:
    - If the answer contains <strong>...</strong>, show only those bold parts.
    - Else, if the answer repeats the question HTML verbatim, strip it.
    - Else, show the full answer as-is.
    """
    q = card.get("front_html", "") or ""
    a = card.get("back_html", "") or ""
    # Prefer bold segments
    hits = re.findall(r"<strong[^>]*>(.*?)</strong>", a, flags=re.I | re.S)
    hits = [h.strip() for h in hits if h and h.strip()]
    if hits:
        return "<br>".join(hits)
    # Strip duplicated question if present
    if q and q in a:
        trimmed = a.replace(q, "").strip()
        if trimmed:
            return trimmed
    return a


CARDS = load_cards_from_module()
CHAPTERS = sorted({c["chapter"] for c in CARDS})


# ---------- Deck builders ----------
def build_deck_within(chapters: list[str]) -> list[int]:
    idx = [i for i, c in enumerate(CARDS) if c["chapter"] in chapters]
    random.shuffle(idx)
    return idx


def build_deck_all_interleaved() -> list[int]:
    by_ch: dict[str, list[int]] = {}
    for i, c in enumerate(CARDS):
        by_ch.setdefault(c["chapter"], []).append(i)
    for lst in by_ch.values():
        random.shuffle(lst)
    deck: list[int] = []
    # Round-robin interleave to avoid long runs from one chapter
    while any(by_ch.values()):
        for ch in list(by_ch.keys()):
            if by_ch[ch]:
                deck.append(by_ch[ch].pop(0))
    return deck


def reset_fc_state():
    for k in ("fc_deck", "fc_i", "fc_flipped", "fc_selected_chapters"):
        st.session_state.pop(k, None)


# ---------- Minimal toolbar ----------
left, right = st.columns([1, 3])
with left:
    selected = st.multiselect(
        "Chapters",
        CHAPTERS,
        default=[],
        placeholder="Pick chapters for 'Test within Chapters'",
    )
with right:
    st.markdown('<div class="toolbar">', unsafe_allow_html=True)
    start_within = st.button("Test within Chapters")
    start_all = st.button("Test All")
    st.markdown("</div>", unsafe_allow_html=True)

if start_within:
    if not selected:
        st.warning("Select at least one chapter.")
    else:
        st.session_state["fc_deck"] = build_deck_within(selected)
        st.session_state["fc_i"] = 0
        st.session_state["fc_flipped"] = False
        st.session_state["fc_selected_chapters"] = list(selected)

if start_all:
    st.session_state["fc_deck"] = build_deck_all_interleaved()
    st.session_state["fc_i"] = 0
    st.session_state["fc_flipped"] = False
    st.session_state["fc_selected_chapters"] = None

# ---------- Card UI + controls ----------
deck = st.session_state.get("fc_deck")

if not CARDS:
    st.error(
        "No flashcards found. Put your JSON files in `modules/FlashCards/data/` (e.g., `ch_00.json`)."
    )
elif not deck:
    st.info("Press **Test within Chapters** or **Test All** to begin.")
else:
    # NAV first (so clicks update state before we render)
    nav1, flip_col, nav2 = st.columns([1, 2, 1])

    # Prev
    if nav1.button("◀ Prev", key="fc_prev"):
        st.session_state["fc_i"] = max(0, st.session_state.get("fc_i", 0) - 1)
        st.session_state["fc_flipped"] = False

    # Flip (toggle state)
    if flip_col.button("Flip", key="fc_flip"):
        st.session_state["fc_flipped"] = not bool(
            st.session_state.get("fc_flipped", False)
        )

    # Next
    if nav2.button("Next ▶", key="fc_next"):
        st.session_state["fc_i"] = min(
            len(deck) - 1, st.session_state.get("fc_i", 0) + 1
        )
        st.session_state["fc_flipped"] = False

    # Read current state
    i = int(st.session_state.get("fc_i", 0))
    i = max(0, min(i, len(deck) - 1))
    st.session_state["fc_i"] = i
    flipped = bool(st.session_state.get("fc_flipped", False))
    card = CARDS[deck[i]]
    content_html = back_html_for(card) if flipped else card["front_html"]

    # Card
    st.markdown('<div class="card-wrap">', unsafe_allow_html=True)
    st.markdown(
        f"""
        <div class="card">
          <div class="hint">{'Back (answer)' if flipped else 'Front (question)'}</div>
          <div class="chapter">{card['chapter']}</div>
          <div class="center">{content_html}</div>
          <div class="progress">{i+1} / {len(deck)}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.markdown("</div>", unsafe_allow_html=True)
