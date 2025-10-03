# pages/1_📚_PDF_Library.py
from pathlib import Path
import io, zipfile
import streamlit as st
from core.pdf_tools import list_pdfs, first_page_text  # already in your project

# ---------- Inline PDF rendering (PyMuPDF) ----------
try:
    import fitz  # PyMuPDF

    HAS_FITZ = True
except Exception:
    HAS_FITZ = False


@st.cache_data(show_spinner=False)
def get_page_count(path_str: str, mtime: float) -> int:
    """Return total page count (cached)."""
    doc = fitz.open(path_str)
    return doc.page_count


@st.cache_data(show_spinner=False)
def render_page_png(
    path_str: str, mtime: float, page_index: int, zoom_percent: int
) -> bytes:
    """
    Render 0-based page_index to PNG bytes (cached).
    Cache key includes mtime so images update if the file changes.
    """
    doc = fitz.open(path_str)
    if page_index < 0 or page_index >= doc.page_count:
        return b""
    page = doc[page_index]
    scale = max(50, min(400, int(zoom_percent))) / 100.0  # clamp 50..400%
    mat = fitz.Matrix(scale, scale)
    pix = page.get_pixmap(matrix=mat, alpha=False)
    return pix.tobytes("png")


# ---------- UI ----------
st.title("📚 PDF Library")

BASE = Path(__file__).parents[1]
LIB = BASE / "data" / "library"
LIB.mkdir(parents=True, exist_ok=True)

st.markdown(
    "**Add your course PDFs here.** Upload individual PDFs or a ZIP containing many PDFs."
)

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
    st.info(
        "No PDFs found yet. Add some via the uploaders above, or copy them into data/library and press R to rerun."
    )
else:
    # Each PDF appears as a full-width expander with big preview + controls
    for p in pdf_paths:
        with st.expander(p.name, expanded=False):
            mtime = p.stat().st_mtime

            if HAS_FITZ:
                # Unique keys per file
                key_suffix = p.name.replace(" ", "_").replace(".", "_")
                page_key = f"page_{key_suffix}"  # widget key for page slider
                zoom_key = f"zoom_{key_suffix}"  # widget key for zoom slider

                # Initialize state BEFORE widgets
                if page_key not in st.session_state:
                    st.session_state[page_key] = 1  # 1-based page for humans
                if zoom_key not in st.session_state:
                    st.session_state[zoom_key] = 160  # default 160%

                # Compute total pages
                try:
                    total = get_page_count(str(p), mtime)
                except Exception as e:
                    total = 1
                    st.warning(f"Could not read PDF: {e}")

                # Controls row (prev / slider / next / zoom)
                c1, c2, c3, c4 = st.columns([1, 6, 1, 2])

                # Prev/Next change state BEFORE sliders are created
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

                # Now create sliders; they own their keys and values
                with c2:
                    page_val = st.slider(
                        "Page",
                        1,
                        max(1, total),
                        value=st.session_state[page_key],
                        key=page_key,  # widget stores to the same key
                    )
                with c4:
                    zoom_val = st.slider(
                        "Zoom (%)",
                        80,
                        300,
                        value=st.session_state[zoom_key],
                        step=10,
                        key=zoom_key,  # widget stores to the same key
                    )

                # Render selected page with selected zoom
                try:
                    png = render_page_png(str(p), mtime, page_val - 1, zoom_val)
                    if png:
                        st.image(png, use_container_width=True)
                    else:
                        st.info("No image for this page.")
                except Exception as e:
                    st.warning(f"Preview failed: {e}")
                    st.code(first_page_text(p), language="markdown")

            else:
                st.info("Install 'pymupdf' for inline preview:  pip install pymupdf")
                st.code(first_page_text(p), language="markdown")

# Optional: manifest for later Tutor indexing
st.markdown("---")
if st.button("Write manifest.json"):
    import json

    manifest = [{"name": p.name} for p in pdf_paths]
    out = LIB / "manifest.json"
    out.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    st.success(f"Wrote {out.relative_to(BASE)}")

st.caption("Tip: You can also drop files directly into data/library on disk.")
