from __future__ import annotations
import os, re, random
import streamlit as st
from dotenv import load_dotenv
import unicodedata
from auth_and_progress import auth_ui, load_progress, save_progress
from csv_loader import load_questions_from_csv  # must support the `calc` column
from supabase import create_client


# Try to load local .env (only works if file exists)
load_dotenv()

# First check Streamlit secrets (cloud)
url = st.secrets.get("SUPABASE_URL", os.getenv("SUPABASE_URL"))
key = st.secrets.get("SUPABASE_ANON_KEY", os.getenv("SUPABASE_ANON_KEY"))

if not url or not key:
    st.error(
        "❌ Supabase is not configured. Please set SUPABASE_URL and SUPABASE_ANON_KEY."
    )
else:
    supabase = create_client(url, key)

    st.set_page_config(
        page_title="Real Estate Exam Questions", page_icon="📚", layout="wide"
    )

FALLBACK_PRIMARY = "OneThousand_MCQ.csv"
FALLBACK_SECONDARY = "sample_questions.csv"

# Title FIRST so the page is never blank
st.title("📚 BC Real Estate Exam MCQ")


# -------------------- Helpers --------------------
# normalize weird whitespace and fix digit/letter run-ons like "200and"


# Map a bunch of invisible spaces to a normal space
_INVISIBLES = {
    ord("\u00a0"): " ",  # NBSP
    ord("\u202f"): " ",  # narrow NBSP
    ord("\u2009"): " ",  # thin space
    ord("\u2007"): " ",  # figure space
    ord("\u200a"): " ",  # hair space
    ord("\u200b"): " ",  # zero-width space
    ord("\u200c"): " ",  # ZWNJ
    ord("\u200d"): " ",  # ZWJ
    ord("\u2060"): " ",  # WORD JOINER
    ord("\ufeff"): " ",  # BOM / ZWNBSP
}


def clean_label(s: str) -> str:
    if not s:
        return s
    # Normalize Unicode, then replace a bunch of invisibles with regular spaces
    s = unicodedata.normalize("NFKC", s).translate(_INVISIBLES)
    # Collapse multiple spaces
    s = re.sub(r"[ \t]+", " ", s)

    # Ensure a space between digits and letters both directions
    s = re.sub(r"(\d)([A-Za-z])", r"\1 \2", s)  # 200and -> 200 and
    s = re.sub(r"([A-Za-z])(\d)", r"\1 \2", s)  # and200 -> and 200

    # Ensure a space before a minus that starts a number, if stuck to previous token
    s = re.sub(r"(\S)([-–—])(\$?\d)", r"\1 \2\3", s)

    return s.strip()


def is_correct_mc_single(question: dict, choice_idx: int) -> bool:
    return int(choice_idx) == int(question["correct_index"])


def _update_progress(qid: str, correct: bool, deck_id: str | None = None):
    p = st.session_state.progress
    p["attempts"] = int(p.get("attempts", 0)) + 1
    p["correct"] = int(p.get("correct", 0)) + (1 if correct else 0)

    seen = set(p.get("seen_ids", []))
    seen.add(qid)
    p["seen_ids"] = list(seen)

    wrong = set(p.get("wrong_ids", []))
    if correct:
        wrong.discard(qid)
    else:
        wrong.add(qid)
    p["wrong_ids"] = list(wrong)

    if deck_id:
        deck = p.setdefault("by_deck", {}).setdefault(
            deck_id, {"attempts": 0, "correct": 0}
        )
        deck["attempts"] += 1
        deck["correct"] += 1 if correct else 0

    save_progress(p)  # guarded in auth_and_progress.py


def mark_attempt(question: dict, selected_choice_idx: int):
    correct = is_correct_mc_single(question, selected_choice_idx)
    _update_progress(question["id"], correct, deck_id=question.get("deck_id"))
    st.session_state["last_submit_correct"] = bool(correct)
    st.session_state["last_submit_qid"] = question["id"]
    return correct


def id_to_int(qid: str) -> int:
    try:
        return int(str(qid).strip())
    except Exception:
        return -1


def clamp_index(i: int, n: int) -> int:
    return max(0, min(i, max(0, n - 1)))


def load_questions_from_disk():
    base = os.path.dirname(__file__)
    p1 = os.path.join(base, FALLBACK_PRIMARY)
    if os.path.exists(p1):
        return load_questions_from_csv(p1)
    p2 = os.path.join(base, FALLBACK_SECONDARY)
    if os.path.exists(p2):
        return load_questions_from_csv(p2)
    return [], [
        {
            "row_num": "-",
            "error": "No CSV found (place OneThousand_QandA.csv next to app.py)",
        }
    ]


# ------- Sticky selection for Random N / Shuffle -------
def _selection_fingerprint():
    return {
        "mode": st.session_state.get("mcq_mode", "All"),
        "range_start": st.session_state.get("mcq_range_start"),
        "range_end": st.session_state.get("mcq_range_end"),
        "random_n": st.session_state.get("mcq_random_n"),
        "shuffle": st.session_state.get("shuffle", False),
    }


def _reset_cached_selection():
    for k in ["_cached_fp", "_cached_ids"]:
        st.session_state.pop(k, None)
    st.session_state["idx"] = 0


def build_worklist(questions: list[dict]) -> list[dict]:
    fp = _selection_fingerprint()
    cached_fp = st.session_state.get("_cached_fp")
    cached_ids = st.session_state.get("_cached_ids")

    mode = fp["mode"]
    shuffle = bool(fp["shuffle"])
    wrong_ids = set(st.session_state.progress.get("wrong_ids", []))
    seen_ids = set(st.session_state.progress.get("seen_ids", []))

    # Build pool per mode (Random N handled later)
    if mode == "All":
        pool = questions
    elif mode == "Range":
        start = int(fp.get("range_start") or 1)
        end = int(fp.get("range_end") or start)
        if start > end:
            start, end = end, start
        pool = [q for q in questions if start <= id_to_int(q["id"]) <= end]
    elif mode == "Wrong only":
        pool = [q for q in questions if q["id"] in wrong_ids]
    elif mode == "Not done yet":
        pool = [q for q in questions if q["id"] not in seen_ids]
    elif mode == "Calculation only":
        pool = [q for q in questions if q.get("is_calc")]
    elif mode == "Non-calculation only":
        pool = [q for q in questions if not q.get("is_calc")]
    elif mode == "Random N":
        pool = questions  # (change to a filtered pool if you want)
    else:
        pool = questions

    # Random N: sample once per Apply/setting change
    if mode == "Random N":
        need_new = (cached_fp != fp) or (cached_ids is None)
        if need_new:
            n = int(fp.get("random_n") or 10)
            n = max(1, min(n, len(pool)))
            sample = random.sample(pool, n)
            ids = [q["id"] for q in sample]
            st.session_state["_cached_ids"] = ids
            st.session_state["_cached_fp"] = fp
        ids = st.session_state["_cached_ids"]
        worklist = [q for q in pool if q["id"] in set(ids)]
        order = {qid: i for i, qid in enumerate(ids)}
        worklist.sort(key=lambda q: order[q["id"]])
        return worklist

    # Non–Random N: also cache order (with optional shuffle)
    need_new = (cached_fp != fp) or (cached_ids is None)
    if need_new:
        ids = [q["id"] for q in pool]
        if shuffle:
            random.shuffle(ids)
        st.session_state["_cached_ids"] = ids
        st.session_state["_cached_fp"] = fp

    ids = st.session_state["_cached_ids"]
    wl = [q for q in pool if q["id"] in set(ids)]
    order = {qid: i for i, qid in enumerate(ids)}
    wl.sort(key=lambda q: order[q["id"]])
    return wl


def jump_to(query: str, worklist: list[dict]) -> int:
    """
    Accepts '47' or 'Q47' or '1000'. Tries by Question_int in the current worklist.
    If ID isn't present in the selection, jump to nearest ID and notify.
    """
    s = (query or "").strip()
    if not s:
        return st.session_state.get("idx", 0)

    m = re.search(r"(\d+)", s)
    if not m:
        return st.session_state.get("idx", 0)
    wanted = int(m.group(1))

    for i, q in enumerate(worklist):
        if id_to_int(q["id"]) == wanted:
            return i

    st.info(
        f"Q{wanted} isn’t in the current selection (mode/filter). Showing nearest available item."
    )
    if worklist:
        wl_ids = [id_to_int(q["id"]) for q in worklist]
        nearest_idx = min(range(len(wl_ids)), key=lambda i: abs(wl_ids[i] - wanted))
        return nearest_idx

    return st.session_state.get("idx", 0)


# -------------------- Auth --------------------
user = auth_ui()
if not user:
    st.info("Sign in from the **sidebar → Account** to continue.")
    st.stop()

# -------------------- Load progress (guarded) --------------------
if "progress_loaded" not in st.session_state:
    st.session_state.progress_loaded = False

if "progress" not in st.session_state or not st.session_state.progress_loaded:
    st.session_state.progress = load_progress()
    st.session_state.progress_loaded = True

# -------------------- Load questions (no upload UI) --------------------
questions, problems = load_questions_from_disk()
if problems:
    with st.sidebar.expander(f"Skipped {len(problems)} bad rows", expanded=False):
        for p in problems[:50]:
            st.write(p)
if not questions:
    st.error("No questions loaded.")
    st.stop()

# -------------------- Settings panel (left) --------------------
st.sidebar.header("Settings")
mode = st.sidebar.radio(
    "Choose set to practice",
    [
        "All",
        "Range",
        "Random N",
        "Wrong only",
        "Not done yet",
        "Calculation only",
        "Non-calculation only",
    ],
    index=[
        "All",
        "Range",
        "Random N",
        "Wrong only",
        "Not done yet",
        "Calculation only",
        "Non-calculation only",
    ].index(st.session_state.get("mcq_mode", "All")),
    key="mode",
)
if mode == "Range":
    st.sidebar.number_input("Start (Question_int)", min_value=1, key="range_start")
    st.sidebar.number_input("End (Question_int)", min_value=1, key="range_end")
if mode == "Random N":
    st.sidebar.number_input(
        "N questions", min_value=1, max_value=len(questions), key="random_n"
    )
st.sidebar.toggle("Shuffle order", key="shuffle")
st.sidebar.toggle("Always show answers", key="always_show")

if st.sidebar.button("Apply selection"):
    _reset_cached_selection()

if st.sidebar.button("Reset progress & settings"):
    st.session_state.progress = {
        "attempts": 0,
        "correct": 0,
        "wrong_ids": [],
        "seen_ids": [],
    }
    save_progress(st.session_state.progress)
    for k in [
        "idx",
        "mode",
        "range_start",
        "range_end",
        "random_n",
        "shuffle",
        "always_show",
        "_cached_fp",
        "_cached_ids",
    ]:
        if k in st.session_state:
            del st.session_state[k]
    st.success("Progress and settings reset")

# -------------------- Worklist & navigation --------------------
worklist = build_worklist(questions)
if not worklist:
    st.warning("No questions in current selection")
    st.stop()

# Nav
t1, t2, t3 = st.columns([1, 2, 1])
with t1:
    if st.button("← Previous"):
        st.session_state["idx"] = clamp_index(
            st.session_state.get("idx", 0) - 1, len(worklist)
        )
with t2:
    goto = st.text_input("Go to (e.g., 47 or Q47)")
    if st.button("Go"):
        st.session_state["idx"] = clamp_index(jump_to(goto, worklist), len(worklist))
with t3:
    if st.button("Next →"):
        st.session_state["idx"] = clamp_index(
            st.session_state.get("idx", 0) + 1, len(worklist)
        )

# Final clamp (if selection changed mid-rerun)
st.session_state["idx"] = clamp_index(st.session_state.get("idx", 0), len(worklist))
idx = st.session_state["idx"]
q = worklist[idx]

# -------------------- Render --------------------
st.subheader(f"Q{q['id']}")
# Render HTML prompt properly (tables, paragraphs)
st.markdown(q["prompt"], unsafe_allow_html=True)

# selected = st.radio(
#     "Choose an answer:",
#     options=list(range(len(q["choices"]))),
#     format_func=lambda i: q["choices"][i],
#     key=f"q_choice_{q['id']}",
# )
selected = st.radio(
    "Choose an answer:",
    options=list(range(len(q["choices"]))),
    format_func=lambda i: clean_label(q["choices"][i]),
    key=f"q_choice_{q['id']}",
)

show_answer = st.session_state.get("always_show", False)

# Reliable feedback: key includes both id and index
if st.button("Submit", key=f"submit_{q['id']}_{idx}"):
    correct = mark_attempt(q, int(selected))
    show_answer = True
    if correct:
        st.success("✅ Correct")
    else:
        st.error(f"❌ Incorrect. Correct answer: {q['choices'][q['correct_index']]}")

if show_answer:
    st.info(f"Correct: {q['choices'][q['correct_index']]}")
    if q.get("explanation_html"):
        st.markdown(q["explanation_html"], unsafe_allow_html=True)

# -------------------- Footer stats --------------------
p = st.session_state.progress
attempts, correct_ct = int(p.get("attempts", 0)), int(p.get("correct", 0))
acc = f"{100*correct_ct/attempts:.1f}%" if attempts else "—"
active_mode = st.session_state.get("mcq_mode", "All")

st.markdown("---")
st.write(
    f"{idx+1} / {len(worklist)} ({active_mode}) • Attempts: {attempts} • Correct: {correct_ct} • Accuracy: {acc}"
)
