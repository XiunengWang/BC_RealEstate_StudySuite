import json
import random
import re
from pathlib import Path
from typing import Dict, List, Tuple, Optional
import streamlit as st

# ============== Page config ==============
st.set_page_config(page_title="RETS Flashcards", layout="wide")

DATA_DIR = Path(__file__).parent / "data"  # expects ch_01.json ... ch_26.json here

# ============== Custom chapter titles (Option A) ==============
CHAPTER_TITLES = {
    1: "Fundamentals of Law",
    2: "The Real Estate Services Act",
    3: "What the Purchaser Buys: Estates and Interests in Land",
    4: "Title Registration in British Columbia",
    5: "The Professional Liability of Real Estate Licensees",
    6: "Commercial and Residential Tenancies",
    7: "Strata Properties (Condominiums) and Co-Operatives in British Columbia",
    8: "Financial Statements",
    9: "Professional Ethics",
    10: "The Law of Contract",
    11: "Contracts for Real Estate Transactions",
    12: "Law of Agency",
    13: "Introduction to Mortgage Finance",
    14: "Interest Rate Analysis and Constant Payment Mortgages",
    15: "Mortgage Law",
    16: "Mortgage Yield and Cost Analysis",
    17: "Mortgage Underwriting and Borrower Qualification",
    18: "Local Government Law",
    19: "Taxes on Real Property",
    20: "Building Design and Construction",
    21: "Introduction to Real Estate Appraisal",
    22: "Comparative and Cost Methods of Appraisal",
    23: "The Income or Investment Method of Appraisal",
    24: "Statements of Adjustment and Completion of the Sale",
    25: "Introduction to Marketing",
    26: "Technology and the Real Estate Licensee",
}
# If you also add a Preface file as data/ch_00.json, uncomment:
CHAPTER_TITLES[0] = "Preface - Introduction to Real Estate"


def chapter_label(n: int) -> str:
    if n == 0:
        return CHAPTER_TITLES.get(0, "Preface - Introduction to Real Estate")
    title = CHAPTER_TITLES.get(n)
    return f"Chapter {n} - {title}" if title else f"Chapter {n}"


# ============== Styles & helpers ==============
# Bold green ONLY inside the Q/A HTML
st.markdown(
    """
<style>
  html, body, .main .block-container { scroll-behavior: smooth; }
  .qa-content strong { color:#16a34a !important; font-weight:700; }
  .jump-preview { border-left: 4px solid #16a34a22; padding-left: 12px; margin: 8px 0 16px; }
  .jump-preview .qa-content { background: #fafafa; border: 1px solid #eee; border-radius: 10px; padding: 12px; }
</style>
""",
    unsafe_allow_html=True,
)

# Escape literal $ so Markdown won't parse LaTeX; otherwise render HTML as-is
_dollar_re = re.compile(r"(?<!\\)\$")


def escape_dollars(s: Optional[str]) -> str:
    return _dollar_re.sub(r"\\$", s or "")


# Query-param helpers (new & old Streamlit)
def set_qp(name: str, value: Optional[str]) -> None:
    try:
        if value is None:
            if name in st.query_params:
                del st.query_params[name]
        else:
            st.query_params[name] = value
    except Exception:
        if value is None:
            st.experimental_set_query_params()
        else:
            st.experimental_set_query_params(**{name: value})


def get_qp(name: str) -> Optional[str]:
    try:
        v = st.query_params.get(name)
        if isinstance(v, list):
            v = v[-1]
        return v
    except Exception:
        return None


def do_rerun() -> None:
    try:
        st.rerun()
    except AttributeError:
        try:
            st.experimental_rerun()  # type: ignore[attr-defined]
        except Exception:
            pass


# Keyboard nav component (runs in an iframe; use window.top to modify parent URL)
st.components.v1.html(
    """
<script>
(function(){
  function go(dir){
    const url = new URL(window.top.location.href);
    url.searchParams.set('nav', dir);
    window.top.location.replace(url.toString());
  }
  window.addEventListener('keydown', function(e){
    if (e.target && ['INPUT','TEXTAREA'].includes(e.target.tagName)) return;
    if (e.key === 'ArrowRight') go('next');
    if (e.key === 'ArrowLeft')  go('prev');
  }, true);
})();
</script>
""",
    height=0,
)


# ============== Data loaders ==============
@st.cache_data(show_spinner=False)
def load_chapter(num: int) -> List[Dict]:
    fn = DATA_DIR / f"ch_{num:02d}.json"
    if not fn.exists():
        return []
    return json.loads(fn.read_text(encoding="utf-8"))


@st.cache_data(show_spinner=False)
def load_all_chapters() -> Dict[int, List[Dict]]:
    data = {}
    # Change 1 to 0 if you add Preface at ch_00.json
    for i in range(0, 27):
        cards = load_chapter(i)
        if cards:
            data[i] = cards
    # If you added Preface:
    # pre = load_chapter(0)
    # if pre: data[0] = pre
    return data


def strip_html_to_text(s: str) -> str:
    s = re.sub(r"<br\s*/?>", " ", s, flags=re.I)
    s = re.sub(r"<.*?>", "", s)
    return re.sub(r"\s+", " ", s).strip()


# ============== Session state ==============
ss = st.session_state
ss.setdefault("chapter", 1)  # default chapter
ss.setdefault("index", 0)
ss.setdefault("show_answer", False)
ss.setdefault("search", "")
ss.setdefault("mode", "Chapter")  # "Chapter" or "All"
ss.setdefault("order", [])  # list[tuple] of (scope, chapter, idx)
ss.setdefault("lock_order", False)  # keeps randomized order across reruns
ss.setdefault("view_counts", {})  # {(ch, idx): count}
ss.setdefault("last_key", None)
ss.setdefault("jump_open_pos", None)  # which Jump item is expanded inline

all_data = load_all_chapters()

# ============== Sidebar ==============
with st.sidebar:
    st.markdown("## Mode")
    new_mode = st.radio(
        "Practice mode", ["Chapter", "All"], index=0, label_visibility="collapsed"
    )
    if new_mode != ss.mode:
        ss.mode = new_mode
        ss.lock_order = False
        ss.jump_open_pos = None

    st.markdown("## Search")
    new_search = st.text_input(
        "Keyword (Q or A)", value=ss.search, placeholder="search…"
    )
    if new_search != ss.search:
        ss.search = new_search
        ss.lock_order = False
        ss.jump_open_pos = None

    if ss.mode == "Chapter":
        st.markdown("## Chapters")
        # Show only chapters that exist AND are in your title map
        available = [n for n in sorted(all_data.keys()) if n in CHAPTER_TITLES]
        # If using Preface, ensure 0 is included appropriately
        selected = st.radio(
            "Select a chapter",
            available,
            format_func=chapter_label,
            index=available.index(ss.chapter) if ss.chapter in available else 0,
            label_visibility="collapsed",
        )
        if selected != ss.chapter:
            ss.chapter = selected
            ss.index = 0
            ss.lock_order = False
            ss.jump_open_pos = None


# ============== Build working set ==============
def build_working_set() -> List[Tuple[str, int, int]]:
    """Return a list of tuples: ('C' or 'A', chapter, index)."""
    if ss.mode == "Chapter":
        cards = all_data.get(ss.chapter, [])
        if ss.search.strip():
            pat = re.compile(re.escape(ss.search.strip()), re.I)
            idxs = [
                i
                for i in range(len(cards))
                if pat.search(cards[i].get("question", ""))
                or pat.search(cards[i].get("answer", ""))
            ]
        else:
            idxs = list(range(len(cards)))
        return [("C", ss.chapter, i) for i in idxs]
    else:
        tuples: List[Tuple[str, int, int]] = []
        for ch, cards in all_data.items():
            if ch not in CHAPTER_TITLES:
                continue
            for i in range(len(cards)):
                tuples.append(("A", ch, i))
        if ss.search.strip():
            pat = re.compile(re.escape(ss.search.strip()), re.I)
            tuples = [
                t
                for t in tuples
                if pat.search(all_data[t[1]][t[2]].get("question", ""))
                or pat.search(all_data[t[1]][t[2]].get("answer", ""))
            ]
        return tuples


def ensure_order() -> None:
    tuples = build_working_set()
    if not ss.order:
        ss.order = tuples
        ss.index = 0
        return

    if ss.lock_order:
        # Keep the shuffled order; drop invalid items
        valid = set(tuples)
        ss.order = [t for t in ss.order if t in valid]
        ss.index = max(0, min(ss.index, len(ss.order) - 1))
        return

    # Rebuild sequential order (when not locked)
    current = ss.order[ss.index] if 0 <= ss.index < len(ss.order) else None
    ss.order = tuples
    ss.index = ss.order.index(current) if current in ss.order else 0


ensure_order()

# Handle keyboard nav (?nav=prev|next)
nav = get_qp("nav")
if nav:
    set_qp("nav", None)
    if ss.order:
        if nav == "next" and ss.index < len(ss.order) - 1:
            ss.index += 1
        if nav == "prev" and ss.index > 0:
            ss.index -= 1
    ss.jump_open_pos = None  # close any inline preview when using keyboard nav

# ============== Toolbar ==============
col_prev, col_next, col_show, col_rand_ch, col_rand_all, col_views = st.columns(
    [1, 1, 1, 1, 1, 1]
)

with col_prev:
    if st.button("← Previous", use_container_width=True, disabled=(ss.index <= 0)):
        ss.index = max(0, ss.index - 1)
        ss.jump_open_pos = None

with col_next:
    if st.button(
        "Next →",
        use_container_width=True,
        disabled=(not ss.order or ss.index >= len(ss.order) - 1),
    ):
        ss.index = min(len(ss.order) - 1, ss.index + 1)
        ss.jump_open_pos = None

with col_show:
    ss.show_answer = st.toggle("Show Answer", value=ss.show_answer)

with col_rand_ch:
    if st.button("Randomize within chapter", use_container_width=True):
        ss.mode = "Chapter"
        ss.lock_order = True
        tuples = build_working_set()
        random.shuffle(tuples)
        ss.order = tuples
        ss.index = 0
        ss.jump_open_pos = None
        do_rerun()

with col_rand_all:
    if st.button("Randomize all", use_container_width=True):
        ss.mode = "All"
        ss.lock_order = True
        tuples = build_working_set()
        random.shuffle(tuples)
        ss.order = tuples
        ss.index = 0
        ss.jump_open_pos = None
        do_rerun()

# ============== Show card ==============
if not ss.order:
    st.info("No cards match your current filters.")
else:
    scope, ch, i = ss.order[ss.index]
    card = all_data[ch][i]

    # View counter (increments only when card actually changes)
    key = (ch, i)
    if ss.last_key != key:
        ss.view_counts[key] = ss.view_counts.get(key, 0) + 1
        ss.last_key = key
    with col_views:
        st.metric("Views", ss.view_counts.get(key, 0))

    # Use your custom title in the header
    if ss.mode == "All":
        label = chapter_label(ch)
    else:
        label = chapter_label(ss.chapter)
    st.markdown(f"### {label} — Card {ss.index+1} of {len(ss.order)}")

    # Two-column Q & A (main display)
    qcol, acol = st.columns(2, gap="large")
    with qcol:
        st.markdown("**Question**")
        st.markdown(
            f"<div class='qa-content'>{escape_dollars(card.get('question',''))}</div>",
            unsafe_allow_html=True,
        )
    with acol:
        st.markdown("**Answer**")
        if ss.show_answer:
            st.markdown(
                f"<div class='qa-content'>{escape_dollars(card.get('answer',''))}</div>",
                unsafe_allow_html=True,
            )
        else:
            st.caption("Answer hidden — toggle 'Show Answer' to reveal.")

    # ========== Jump list with inline expansion ==========
    with st.expander("Jump to…"):
        for pos, tup in enumerate(ss.order):
            _, ch2, i2 = tup
            qtext = strip_html_to_text(all_data[ch2][i2].get("question", ""))
            if len(qtext) > 120:
                qtext = qtext[:117] + "…"
            prefix = f"[{chapter_label(ch2)}] " if ss.mode == "All" else ""
            # Each item: button + optional inline preview right under it
            if st.button(f"{prefix}{pos+1}. {qtext}", key=f"jump_{ch2}_{i2}"):
                ss.index = pos
                ss.jump_open_pos = pos  # expand this item inline
                # Streamlit reruns automatically on button click

            if ss.jump_open_pos == pos:
                # Full Q & A inline (always show both, per your request)
                with st.container(border=False):
                    st.markdown("<div class='jump-preview'>", unsafe_allow_html=True)
                    st.markdown("**Question**")
                    st.markdown(
                        f"<div class='qa-content'>{escape_dollars(all_data[ch2][i2].get('question',''))}</div>",
                        unsafe_allow_html=True,
                    )
                    st.markdown("**Answer**")
                    st.markdown(
                        f"<div class='qa-content'>{escape_dollars(all_data[ch2][i2].get('answer',''))}</div>",
                        unsafe_allow_html=True,
                    )
                    # Close preview
                    if st.button("Close preview", key=f"close_{ch2}_{i2}"):
                        ss.jump_open_pos = None
                        do_rerun()
                    st.markdown("</div>", unsafe_allow_html=True)
