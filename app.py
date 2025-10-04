import sys
from pathlib import Path
import streamlit as st

st.set_page_config(page_title="Study Suite", page_icon="🎒", layout="wide")


APP_DIR = Path(__file__).parent

# Example: reading the question bank
CSV_PATH = APP_DIR / "OneThousand_MCQ.csv"
# e.g., df = pd.read_csv(CSV_PATH)


MCQ_DIR = Path(__file__).parent / "modules" / "MCQ"
if str(MCQ_DIR) not in sys.path:
    sys.path.insert(0, str(MCQ_DIR))

try:
    from auth_and_progress import auth_ui, current_user_id

    AUTH_AVAILABLE = True
except Exception as e:
    AUTH_AVAILABLE = False
    AUTH_ERR = e

st.title("Study Suite")
st.caption("MCQ • Flashcards • Mindmaps • PDF • Tutor")

with st.sidebar:
    st.header("Account")
    if AUTH_AVAILABLE:
        _ = auth_ui()  # renders its own status + logout
    else:
        st.error("Authentication module not available.")
        st.caption(f"{AUTH_ERR}")

st.subheader("Open a tool")
col1, col2, col3 = st.columns(3)
with col1:
    st.page_link("pages/2_MCQ.py", label="MCQ")
    st.page_link("pages/3_Flashcards.py", label="Flashcards")
with col2:
    st.page_link("pages/4_Mindmaps.py", label="Mindmaps")
    st.page_link("pages/1_PDF_Library.py", label="PDF Library")
with col3:
    st.page_link("pages/5_Tutor.py", label="Tutor")

st.markdown("---")
st.markdown(
    "Setup notes:\n"
    "- Put your Streamlit Secrets or `.env` with SUPABASE_URL and SUPABASE_ANON_KEY for login.\n"
    "- MCQ progress will continue to use your existing Supabase tables.\n"
    "- Flashcards/Mindmaps are wrapped as pages.\n"
    "- PDF and Tutor pages are ready; PDF has inline preview (pymupdf)."
)
