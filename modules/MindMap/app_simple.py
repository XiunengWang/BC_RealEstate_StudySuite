
import re
import zipfile
from pathlib import Path
from typing import List, Tuple

import streamlit as st
from streamlit.components.v1 import html as st_html

st.set_page_config(page_title="BC Real Estate Chapters — Mind Maps", layout="wide")

def ensure_extracted(zip_path: Path, extract_dir: Path) -> list[Path]:
    extract_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, "r") as zf:
        html_members = [m for m in zf.namelist() if m.lower().endswith(".html")]
        for m in html_members:
            target = extract_dir / Path(m).name
            if not target.exists():
                with zf.open(m) as src, open(target, "wb") as dst:
                    dst.write(src.read())
    return sorted(extract_dir.glob("*.html"))

def html_title(html: str, fallback: str) -> str:
    m = re.search(r"(?is)<title>(.*?)</title>", html)
    if m:
        return re.sub(r"\s+", " ", m.group(1)).strip() or fallback
    return fallback

def read_text(p: Path) -> str:
    return p.read_text(encoding="utf-8", errors="ignore")

default_zip = Path(__file__).parent / "BCRealEstateChapters_mindmap.zip"
if not default_zip.exists():
    st.error("BCRealEstateChapters_mindmap.zip not found next to this app.")
    st.stop()

extract_dir = Path.cwd() / ".mindmaps_simple" / "default"
html_files = ensure_extracted(default_zip, extract_dir)

if not html_files:
    st.error("No HTML files found in BCRealEstateChapters_mindmap.zip")
    st.stop()

titles = []
for p in html_files:
    try:
        titles.append(html_title(read_text(p), p.stem))
    except Exception:
        titles.append(p.stem)

st.sidebar.title("Chapters")
options = [(i, titles[i]) for i in range(len(titles))]
selected = st.sidebar.radio("Pick a chapter", options=options, format_func=lambda x: x[1], index=0, label_visibility="collapsed")

sel_idx = selected[0]
selected_file = html_files[sel_idx]

st.header(titles[sel_idx])
html_content = read_text(selected_file)

wrapper = f"""
<!doctype html>
<html>
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <style>
      html, body {{ margin: 0; padding: 0; height: 100%; }}
      .container {{
        position: relative;
        width: 100%;
        height: 100%;
        overflow: auto;
      }}
      .container svg, .container canvas {{
        display: block;
      }}
    </style>
  </head>
  <body>
    <div class="container">
      {html_content}
    </div>
  </body>
</html>
"""
st_html(wrapper, height=900, scrolling=True)
