
from pathlib import Path
from typing import List, Dict
from pypdf import PdfReader

def list_pdfs(folder: Path) -> List[Path]:
    folder.mkdir(parents=True, exist_ok=True)
    return sorted([p for p in folder.glob("*.pdf") if p.is_file()])

def pdf_info(pdf_path: Path) -> Dict:
    try:
        reader = PdfReader(str(pdf_path))
        pages = len(reader.pages)
        title = reader.metadata.get("/Title") if reader.metadata else None
        return {"name": pdf_path.name, "pages": pages, "title": title or ""}
    except Exception as e:
        return {"name": pdf_path.name, "pages": 0, "title": "", "error": str(e)}

def first_page_text(pdf_path: Path, max_chars: int = 800) -> str:
    try:
        reader = PdfReader(str(pdf_path))
        if len(reader.pages) == 0:
            return ""
        text = reader.pages[0].extract_text() or ""
        return text[:max_chars]
    except Exception:
        return ""
