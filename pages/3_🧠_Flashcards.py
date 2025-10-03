
from pathlib import Path
import streamlit as st
from core.runner import run_flashcards_app, require_login

FLASH_DIR = Path(__file__).parents[1] / "modules" / "FlashCards"

st.title("🧠 Flashcards")
if require_login():
    run_flashcards_app(FLASH_DIR)
