from __future__ import annotations
import csv
import io
import os
import re
import unicodedata
from typing import List, Tuple, Dict, Any

# Optional but recommended: auto-detect encoding
try:
    from charset_normalizer import (
        from_bytes as cn_from_bytes,
    )  # pip install charset-normalizer>=3.3
except Exception:
    cn_from_bytes = None

# If you use Streamlit, we can surface friendly warnings; otherwise no-ops
try:
    import streamlit as st
except Exception:

    class _Stub:
        def warning(self, *a, **k):
            pass

        def info(self, *a, **k):
            pass

        def error(self, *a, **k):
            pass

    st = _Stub()

# --------- Unicode cleanup helpers ---------
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


def _normalize_text(s: str) -> str:
    if s is None:
        return ""
    s = unicodedata.normalize("NFKC", s)
    s = s.translate(_INVISIBLES)
    return s


# --------- Encoding-robust file read ---------
def _read_csv_text(csv_path: str) -> str:
    """
    Read CSV file text robustly:
    - Try UTF-8 with BOM first
    - If that fails, use charset-normalizer if available
    - Otherwise fall back to latin1 (never fails)
    """
    # 1) Fast path: UTF-8 (accept BOM)
    try:
        with open(csv_path, "r", encoding="utf-8-sig", newline="") as f:
            return f.read()
    except UnicodeDecodeError:
        pass
    except FileNotFoundError:
        raise

    # 2) charset-normalizer (if installed)
    if cn_from_bytes is not None:
        try:
            with open(csv_path, "rb") as fb:
                raw = fb.read()
            probe = cn_from_bytes(raw).best()
            if probe and probe.encoding:
                enc = probe.encoding
                try:
                    return raw.decode(enc, errors="strict")
                except UnicodeDecodeError:
                    st.warning(
                        f"Decoded with '{enc}' using replacement for invalid bytes."
                    )
                    return raw.decode(enc, errors="replace")
        except Exception:
            pass

    # 3) Last resort: latin1
    st.warning("Decoding CSV with latin1 fallback.")
    with open(csv_path, "r", encoding="latin1", newline="") as f:
        return f.read()


# --------- Row parsing (match your schema) ---------
def parse_correct_index(answer_field: str) -> int:
    """
    Accepts either:
      - integer index as string ('3' meaning zero-based? or 1-based?), or
      - 'Correct Option: 4' style (1-based)
    Returns zero-based index.
    """
    s = _normalize_text(answer_field or "").strip()
    if not s:
        raise ValueError("Empty answer field")
    # Try "Correct Option: 4" pattern
    m = re.search(r"(\d+)", s)
    if not m:
        raise ValueError(f"Cannot parse correct option from: {s}")
    idx1 = int(m.group(1))
    if idx1 <= 0:
        raise ValueError(f"Correct option must be >= 1, got {idx1}")
    return idx1 - 1


def parse_choices(choices_text: str) -> List[str]:
    """
    Choices are pipe-separated. Keep inner spaces; strip Excel's leading apostrophe; normalize invisible spaces.
    """
    raw = choices_text or ""
    parts = raw.split("|")
    cleaned = []
    for c in parts:
        if c is None:
            continue
        c = _normalize_text(c)
        if c.startswith("'"):  # Excel "Text" marker
            c = c[1:]
        # Keep inner spacing; only lstrip so " | foo" is okay, but inner 'and ' stays
        c = c.lstrip()
        cleaned.append(c)
    return [x for x in cleaned if x.strip() != ""]


def row_to_question(row: Dict[str, Any]) -> Dict[str, Any]:
    """
    Build the question dict your app expects.
    Required CSV columns (case-sensitive): question, choices, answer, Question_int
    Optional: back, calc
    """
    qtext = _normalize_text(row.get("question", ""))
    choices = parse_choices(row.get("choices", ""))
    if not choices:
        raise ValueError("No choices parsed")

    correct_index = parse_correct_index(row.get("answer", ""))

    # optional explanation/back; render as HTML later
    back_html = _normalize_text(row.get("back", ""))

    # calc flag can be '1', 'true', 'yes', etc.
    calc_raw = str(row.get("calc", "")).strip().lower()
    is_calc = calc_raw in ("1", "true", "yes", "y", "t")

    # Question_int / id
    qid_raw = row.get("Question_int") or row.get("id") or row.get("qid")
    if qid_raw is None or str(qid_raw).strip() == "":
        raise ValueError("Missing Question_int")
    try:
        qid = int(str(qid_raw).strip())
    except Exception:
        raise ValueError(f"Invalid Question_int: {qid_raw}")

    return {
        "id": str(qid),
        "prompt": qtext,  # may include HTML (e.g., j<sub>12</sub>)
        "choices": choices,
        "correct_index": int(correct_index),
        "explanation_html": back_html,  # safe-rendered with unsafe_allow_html=True
        "is_calc": is_calc,
        "deck_id": None,  # optional; keep for progress bucketing
    }


# --------- Public API ---------
def load_questions_from_csv(
    csv_path: str,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Load questions robustly from CSV.
    Returns (questions, problems) where problems is a list of {"row_num", "error", "row"}.
    """
    if not os.path.exists(csv_path):
        raise FileNotFoundError(f"CSV not found at: {csv_path}")

    text = _read_csv_text(csv_path)
    sio = io.StringIO(text)

    reader = csv.DictReader(sio)
    questions: List[Dict[str, Any]] = []
    problems: List[Dict[str, Any]] = []

    # Basic header sanity
    headers = [h.strip() for h in (reader.fieldnames or [])]
    expected = {"question", "choices", "answer", "Question_int"}
    missing = expected - set(headers)
    if missing:
        st.warning(f"CSV missing expected columns: {sorted(missing)}")

    for i, row in enumerate(
        reader, start=2
    ):  # start=2 so row_num matches spreadsheet line numbers
        try:
            q = row_to_question(row)
            # bounds-check correct index
            if not (0 <= q["correct_index"] < len(q["choices"])):
                raise ValueError(
                    f"correct_index {q['correct_index']} out of range for {len(q['choices'])} choices"
                )
            questions.append(q)
        except Exception as e:
            # record the problem but don't crash the app
            problems.append({"row_num": i, "error": str(e), "row": dict(row)})

    return questions, problems
