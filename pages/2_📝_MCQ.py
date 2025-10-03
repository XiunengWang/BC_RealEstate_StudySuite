
from pathlib import Path
import streamlit as st
from core.runner import run_mcq_app, require_login

MCQ_DIR = Path(__file__).parents[1] / "modules" / "BC-real-estate-exam-MCQ-main" / "BC-real-estate-exam-MCQ-main"

st.title("📝 MCQ")
if require_login():
    run_mcq_app(MCQ_DIR)
