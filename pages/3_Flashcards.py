from __future__ import annotations

from pathlib import Path
import json
import random
import re
import streamlit as st
import streamlit.components.v1 as components

# ---------- Page setup ----------
st.set_page_config(page_title="Flashcards", layout="wide")

# Your existing data: modules/FlashCards/data/ch_*.json with keys question/answer (HTML)
MODULE_DATA_DIR = Path(__file__).parents[1] / "modules" / "FlashCards" / "data"


# ---------- Theme helpers ----------
def _hex_to_rgba(hex_color: str, alpha: float) -> str:
    h = (hex_color or "").lstrip("#")
    if len(h) == 3:
        h = "".join([c * 2 for c in h])
    if len(h) != 6:
        return f"rgba(154,160,166,{alpha})"
    r = int(h[0:2], 16)
    g = int(h[2:4], 16)
    b = int(h[4:6], 16)
    return f"rgba({r},{g},{b},{alpha})"


def _opt(key: str, default: str) -> str:
    try:
        v = st.get_option(key)
        if v is None or v == "" or str(v).lower() == "none":
            return default
        return v
    except Exception:
        return default


# Pull individual theme options safely
PRIMARY = _opt("theme.primaryColor", "#3b82f6")
BG_CARD = _opt("theme.secondaryBackgroundColor", "#262730")
TXT = _opt("theme.textColor", "#fafafa")
TXT_MUTED = _hex_to_rgba(TXT, 0.65)
TXT_MUTED_BG = _hex_to_rgba(TXT, 0.10)
BORDER = _hex_to_rgba(TXT, 0.25)
HOVER_BG = _hex_to_rgba(TXT, 0.06)

# ---------- Page-level CSS (toolbar/controls) ----------
st.markdown(
    f"""
<style>
.page-title {{ color: {TXT}; margin-bottom: .25rem; }}

/* Toolbar */
.toolbar {{ display:flex; gap:.75rem; align-items:center; justify-content:center; margin:.25rem 0 .25rem; }}
.toolbar .stButton > button {{
  background: transparent; color: {TXT}; border:1px solid {BORDER}; border-radius:10px; padding:.55rem .9rem;
}}
.toolbar .stButton > button:hover {{ background: {HOVER_BG}; }}

/* Compact centered controls under the card */
.controls-outer {{ display:grid; grid-template-columns: 1fr min(360px, 80vw) 1fr; }}
.controls-inner {{ display:grid; grid-template-columns: 1fr 1fr 1fr; gap:.5rem; }}
.controls-inner .stButton > button {{
  background: transparent; border:1px solid {BORDER}; color: {TXT};
  border-radius: 9999px; padding:.55rem .9rem; cursor:pointer;
}}
.controls-inner .stButton > button:hover {{ background: {HOVER_BG}; }}

/* Multiselect tags dark-friendly */
.stMultiSelect [data-baseweb="tag"] {{ background:{_hex_to_rgba(TXT,0.12)}; color: {TXT}; }}
</style>
""",
    unsafe_allow_html=True,
)

st.markdown('<h1 class="page-title">Flashcards</h1>', unsafe_allow_html=True)


# ---------- Data loading ----------
@st.cache_data(show_spinner=False)
def load_cards_from_module() -> list[dict]:
    cards: list[dict] = []
    if not MODULE_DATA_DIR.exists():
        return cards
    for jf in sorted(MODULE_DATA_DIR.glob("*.json")):
        try:
            data = json.loads(jf.read_text(encoding="utf-8"))
        except Exception:
            continue
        chapter = infer_chapter_name(jf.stem)
        for row in data:
            q_raw = row.get("question", "")
            a_raw = row.get("answer", "")
            q = normalize_html(q_raw)
            a = normalize_html(a_raw)
            if q or a:
                cards.append({"chapter": chapter, "front_html": q, "back_html": a})
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
    # Add space when text touches <strong> boundaries like "a<strong>word</strong>b"
    s = re.sub(r"([A-Za-z0-9])<\s*strong\b", r"\1 <strong", s)
    s = re.sub(r"</\s*strong>([A-Za-z0-9])", r"</strong> \1", s)

    # Keep multi-word strong inline (collapse <br> inside)
    def _fix_strong(m: re.Match) -> str:
        inner = re.sub(r"<br\s*/?>", " ", m.group(1))
        inner = re.sub(r"\s+", " ", inner).strip()
        return f"<strong>{inner}</strong>"

    s = re.sub(r"<strong[^>]*>(.*?)</strong>", _fix_strong, s, flags=re.I | re.S)
    return s


def back_html_for(card: dict) -> str:
    """Prefer bold parts; else strip duplicated question; else show full answer."""
    q = card.get("front_html", "") or ""
    a = card.get("back_html", "") or ""
    hits = re.findall(r"<strong[^>]*>(.*?)</strong>", a, flags=re.I | re.S)
    hits = [h.strip() for h in hits if h and h.strip()]
    if hits:
        return "<br>".join(hits)
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
    while any(by_ch.values()):
        for ch in list(by_ch.keys()):
            if by_ch[ch]:
                deck.append(by_ch[ch].pop(0))
    return deck


# ---------- Toolbar ----------
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
    cA, cB = st.columns([1, 1])
    with cA:
        start_within = st.button("Test within Chapters")
    with cB:
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

# ---------- Card UI (component: click-to-flip) + compact controls ----------
deck = st.session_state.get("fc_deck")

if not CARDS:
    st.error(
        "No flashcards found. Put your JSON files in `modules/FlashCards/data/` (e.g., `ch_00.json`)."
    )
elif not deck:
    st.info("Press **Test within Chapters** or **Test All** to begin.")
else:
    # Read current state
    i = int(st.session_state.get("fc_i", 0))
    i = max(0, min(i, len(deck) - 1))
    st.session_state["fc_i"] = i
    flipped = bool(st.session_state.get("fc_flipped", False))
    card = CARDS[deck[i]]
    content_html = back_html_for(card) if flipped else card["front_html"]

    # Render the card as an HTML component that sends "flip" on click (back-compat postMessage)
    card_height = 420  # px
    comp_val = components.html(
        f"""
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8"/>
<style>
  :root {{
    --card-bg: {BG_CARD};
    --card-fg: {TXT};
    --muted: {TXT_MUTED};
    --accent: {PRIMARY};
    --hint-bg: {TXT_MUTED_BG};
  }}
  body {{ margin:0; padding:0; background: transparent; color: var(--card-fg); font-family: system-ui, -apple-system, Segoe UI, Roboto, Arial, sans-serif; }}
  .wrap {{ display:flex; justify-content:center; }}
  .card {{
    width: min(1100px, 92vw);
    min-height: {card_height - 24}px;  /* minus padding/margins for the iframe */
    background: var(--card-bg);
    color: var(--card-fg);
    border-radius: 18px;
    box-shadow: 0 30px 80px rgba(0,0,0,.35);
    margin: 0.2rem auto 0;
    padding: clamp(28px, 4vw, 56px);
    position: relative;
    cursor: pointer; /* clickable */
  }}
  .hint {{ position:absolute; top:12px; left:18px; color: var(--muted); font-size:.85rem; }}
  .progress {{ position:absolute; bottom:12px; left:18px; color: var(--muted); font-size:.85rem; }}
  .chapter {{ position:absolute; top:12px; right:18px; color: rgba(255,255,255,.8); font-size:.85rem; }}
  .center {{
    display:block; text-align:center; min-height: 260px;
    font-size: clamp(22px, 2.2vw, 36px); line-height: 1.45; white-space: normal; word-break: normal;
  }}
  .center strong, .center b {{ color: #22c55e; font-weight: 800; }}
  .clickhint {{
    position:absolute; left:0; right:0; bottom:0;
    padding:.55rem 1rem; text-align:center; font-weight:700; border-radius:0 0 18px 18px;
    background: var(--hint-bg); color: var(--card-fg);
  }}
</style>
</head>
<body>
  <div class="wrap">
    <div id="card" class="card" role="button" tabindex="0" aria-label="Flashcard">
      <div class="hint">{'Back (answer)' if flipped else 'Front (question)'}</div>
      <div class="chapter">{card['chapter']}</div>
      <div class="center">{content_html}</div>
      <div class="progress">{i+1} / {len(deck)}</div>
      <div class="clickhint">Click on the card to flip</div>
    </div>
  </div>

  <script>
    function sendFlip() {{
      // Older Streamlit html() expects a postMessage protocol like this:
      const msg = {{ isStreamlitMessage: true, type: "streamlit:setComponentValue", value: "flip" }};
      if (window.parent) window.parent.postMessage(msg, "*");
    }}
    const el = document.getElementById("card");
    el.addEventListener("click", sendFlip);
    el.addEventListener("keydown", (e) => {{
      if (e.code === "Space" || e.code === "Enter" || e.key === " ") {{
        e.preventDefault(); sendFlip();
      }}
    }});
  </script>
</body>
</html>
        """,
        height=card_height,
        scrolling=False,  # NOTE: no key=... here
    )

    # When the component reports "flip", toggle and rerun
    if comp_val == "flip":
        st.session_state["fc_flipped"] = not flipped
        st.rerun()

    # Compact centered control row (Prev / Flip / Next)
    st.markdown('<div class="controls-outer">', unsafe_allow_html=True)
    _, controls_col, _ = st.columns([1, 1, 1])
    with controls_col:
        st.markdown('<div class="controls-inner">', unsafe_allow_html=True)
        c1, c2, c3 = st.columns(3)

        with c1:
            if st.button("◀ Prev", key="fc_prev"):
                st.session_state["fc_i"] = max(0, i - 1)
                st.session_state["fc_flipped"] = False
                st.rerun()

        with c2:
            if st.button("Flip", key="fc_flip"):
                st.session_state["fc_flipped"] = not flipped
                st.rerun()

        with c3:
            if st.button("Next ▶", key="fc_next"):
                st.session_state["fc_i"] = min(len(deck) - 1, i + 1)
                st.session_state["fc_flipped"] = False
                st.rerun()

        st.markdown("</div>", unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)
