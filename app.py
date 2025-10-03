import sys
from pathlib import Path
import streamlit as st

st.set_page_config(page_title="Study Suite", page_icon="🎒", layout="wide")

MCQ_DIR = (
    Path(__file__).parent
    / "modules"
    / "BC-real-estate-exam-MCQ-main"
    / "BC-real-estate-exam-MCQ-main"
)
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
        _ = auth_ui()  # renders its own status + logout; don't print another message
    else:
        st.error("Authentication module not available.")
        st.caption(f"{AUTH_ERR}")


st.subheader("Open a tool")
col1, col2, col3 = st.columns(3)
with col1:
    st.page_link("pages/2_📝_MCQ.py", label="MCQ", icon="📝")
    st.page_link("pages/3_🧠_Flashcards.py", label="Flashcards", icon="🧠")
with col2:
    st.page_link("pages/4_🌳_Mindmaps.py", label="Mindmaps", icon="🌳")
    st.page_link("pages/1_📚_PDF_Library.py", label="PDF Library", icon="📚")
with col3:
    st.page_link("pages/5_🤖_Tutor.py", label="Tutor", icon="🤖")

st.markdown("---")
st.markdown(
    "Setup notes:\\n"
    "- Put your Streamlit Secrets or `.env` with SUPABASE_URL and SUPABASE_ANON_KEY for login.\\n"
    "- MCQ progress will continue to use your existing Supabase tables.\\n"
    "- Flashcards/Mindmaps are wrapped as pages.\\n"
    "- PDF and Tutor are placeholders for now."
)
