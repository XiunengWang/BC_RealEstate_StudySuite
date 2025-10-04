
from pathlib import Path
import streamlit as st
from core.runner import run_mindmap_app, require_login

MIND_DIR = Path(__file__).parents[1] / "modules" / "MindMap"

st.title("Mindmaps")
if require_login():
    run_mindmap_app(MIND_DIR)
