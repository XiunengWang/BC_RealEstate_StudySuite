from pathlib import Path
import io, zipfile
import streamlit as st
from core.pdf_tools import list_pdfs, first_page_text

# Inline rendering via PyMuPDF
try:
    import fitz  # PyMuPDF

    HAS_FITZ = True
except Exception:
    HAS_FITZ = False


@st.cache_data(show_spinner=False)
def get_page_count(path_str: str, mtime: float) -> int:
    doc = fitz.open(path_str)
    return doc.page_count


@st.cache_data(show_spinner=False)
def render_page_png(
    path_str: str, mtime: float, page_index: int, zoom_percent: int
) -> bytes:
    doc = fitz.open(path_str)
    if page_index < 0 or page_index >= doc.page_count:
        return b""
    page = doc[page_index]
    scale = max(50, min(400, int(zoom_percent))) / 100.0
    mat = fitz.Matrix(scale, scale)
    pix = page.get_pixmap(matrix=mat, alpha=False)
    return pix.tobytes("png")


st.title("PDF Library")
BASE = Path(__file__).parents[1]
LIB = BASE / "data" / "library"
LIB.mkdir(parents=True, exist_ok=True)

tab1, tab2 = st.tabs(["Upload PDFs", "Upload ZIP of PDFs"])
with tab1:
    files = st.file_uploader(
        "Select one or more PDFs", type=["pdf"], accept_multiple_files=True
    )
    if files and st.button("Save to Library"):
        for f in files:
            (LIB / f.name).write_bytes(f.getbuffer())
        st.success(f"Saved {len(files)} file(s) to data/library")
with tab2:
    z = st.file_uploader(
        "Select a ZIP that contains PDFs", type=["zip"], accept_multiple_files=False
    )
    if z and st.button("Extract ZIP to Library"):
        data = io.BytesIO(z.getvalue())
        count = 0
        with zipfile.ZipFile(data) as zf:
            for info in zf.infolist():
                if info.filename.lower().endswith(".pdf") and not info.is_dir():
                    out = LIB / Path(info.filename).name
                    with zf.open(info) as src, open(out, "wb") as dst:
                        dst.write(src.read())
                        count += 1
        st.success(f"Extracted {count} PDF(s) into data/library")

st.markdown("---")
st.subheader("Library contents")
pdf_paths = list_pdfs(LIB)

if not pdf_paths:
    st.info("No PDFs found yet. Add some above or drop into data/library and rerun.")
else:
    for p in pdf_paths:
        with st.expander(p.name, expanded=False):
            mtime = p.stat().st_mtime
            if HAS_FITZ:
                key_suffix = p.name.replace(" ", "_").replace(".", "_")
                page_key = f"page_{key_suffix}"
                zoom_key = f"zoom_{key_suffix}"
                if page_key not in st.session_state:
                    st.session_state[page_key] = 1
                if zoom_key not in st.session_state:
                    st.session_state[zoom_key] = 160
                try:
                    total = get_page_count(str(p), mtime)
                except Exception as e:
                    total = 1
                    st.warning(f"Could not read PDF: {e}")
                c1, c2, c3, c4 = st.columns([1, 6, 1, 2])
                with c1:
                    if (
                        st.button("◀", key=f"prev_{key_suffix}")
                        and st.session_state[page_key] > 1
                    ):
                        st.session_state[page_key] -= 1
                with c3:
                    if st.button("▶", key=f"next_{key_suffix}") and st.session_state[
                        page_key
                    ] < max(1, total):
                        st.session_state[page_key] += 1
                with c2:
                    st.slider("Page", 1, max(1, total), key=page_key)
                with c4:
                    st.slider("Zoom (%)", 80, 300, step=10, key=zoom_key)
                try:
                    png = render_page_png(
                        str(p),
                        mtime,
                        st.session_state[page_key] - 1,
                        st.session_state[zoom_key],
                    )
                    if png:
                        st.image(png, width="stretch")

                    else:
                        st.info("No image for this page.")
                except Exception as e:
                    st.warning(f"Preview failed: {e}")
                    st.code(first_page_text(p), language="markdown")
            else:
                st.info("Install 'pymupdf' for inline preview:  pip install pymupdf")
                st.code(first_page_text(p), language="markdown")

st.caption("Tip: drop files directly into data/library on disk if you prefer.")
