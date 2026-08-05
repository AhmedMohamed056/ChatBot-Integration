"""Document loading and knowledge-base indexing helpers."""

from __future__ import annotations

import csv
import os
import shutil
import time
from pathlib import Path

from langchain_community.document_loaders import PyMuPDFLoader, TextLoader
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

STATIC_DOCS_DIR = str(Path(__file__).resolve().parent / "static_pdfs")
SUPPORTED_UPLOAD_EXTENSIONS = {".pdf", ".docx", ".doc", ".txt", ".csv", ".xlsx"}


def get_supported_document_type(filename: str) -> str:
    suffix = Path(filename).suffix.lower()
    return suffix.lstrip(".").upper() if suffix in SUPPORTED_UPLOAD_EXTENSIONS else "UNKNOWN"


def load_docx_text(path: str) -> list[Document]:
    try:
        from docx import Document as DocxDocument
    except ImportError as exc:
        raise RuntimeError("python-docx is required for DOCX files") from exc

    doc = DocxDocument(path)
    text = "\n".join(p.text for p in doc.paragraphs if p.text.strip())
    if not text.strip():
        return []
    return [Document(page_content=text, metadata={"source": path})]


def load_doc_text(path: str) -> list[Document]:
    try:
        import textract
    except ImportError:
        return load_docx_text(path)

    raw = textract.process(path)
    text = raw.decode("utf-8", errors="ignore").strip()
    if not text:
        return []
    return [Document(page_content=text, metadata={"source": path})]


def load_csv_text(path: str) -> list[Document]:
    rows = []
    with open(path, newline="", encoding="utf-8-sig") as handle:
        reader = csv.reader(handle)
        for row in reader:
            rows.append(" | ".join(cell.strip() for cell in row if cell.strip()))
    text = "\n".join(rows).strip()
    if not text:
        return []
    return [Document(page_content=text, metadata={"source": path})]


def load_xlsx_text(path: str) -> list[Document]:
    try:
        from openpyxl import load_workbook
    except ImportError as exc:
        raise RuntimeError("openpyxl is required for XLSX files") from exc

    workbook = load_workbook(path, read_only=True, data_only=True)
    chunks: list[str] = []
    for sheet in workbook.worksheets:
        for row in sheet.iter_rows(values_only=True):
            values = [str(cell).strip() for cell in row if cell is not None and str(cell).strip()]
            if values:
                chunks.append(" | ".join(values))
    workbook.close()
    text = "\n".join(chunks).strip()
    if not text:
        return []
    return [Document(page_content=text, metadata={"source": path})]


def load_documents(path: str) -> list[Document]:
    suffix = Path(path).suffix.lower()
    if suffix == ".pdf":
        return PyMuPDFLoader(path).load()
    if suffix == ".txt":
        return TextLoader(path, encoding="utf-8").load()
    if suffix == ".docx":
        return load_docx_text(path)
    if suffix == ".doc":
        return load_doc_text(path)
    if suffix == ".csv":
        return load_csv_text(path)
    if suffix == ".xlsx":
        return load_xlsx_text(path)
    raise ValueError(f"Unsupported file type: {suffix}")


def split_documents(documents: list[Document]) -> list[Document]:
    splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=150)
    return splitter.split_documents(documents)


def split_file(path: str) -> list[Document]:
    docs = load_documents(path)
    if not docs:
        return []
    return split_documents(docs)


def list_supported_files() -> list[Path]:
    directory = Path(STATIC_DOCS_DIR)
    if not directory.exists():
        return []
    return sorted(
        path for path in directory.iterdir()
        if path.is_file() and path.suffix.lower() in SUPPORTED_UPLOAD_EXTENSIONS
    )


def _force_rmtree(path: str) -> bool:
    """Best-effort recursive delete that tolerates Windows file locks.

    Returns True if the directory was removed (or never existed), False if it
    could not be cleared because another process holds a handle on it. Callers
    use the False case to degrade gracefully instead of crashing startup.
    """
    if not os.path.exists(path):
        return True

    def _on_error(func, target, exc_info):
        # Clear the read-only bit (common on Windows) and retry once.
        import stat
        try:
            os.chmod(target, stat.S_IWRITE)
            func(target)
        except Exception:
            pass

    for _ in range(3):
        shutil.rmtree(path, onerror=_on_error)
        if not os.path.exists(path):
            return True
        time.sleep(0.5)
    return not os.path.exists(path)


def rebuild_vectordb(embedding_function, db_dir: str):
    from langchain_chroma import Chroma

    # Try to clear the old index. On Windows, Chroma's SQLite/HNSW files stay
    # locked while any other process (a lingering server instance, a worker)
    # holds the store open — rmtree then raises WinError 32. Rather than let
    # that crash application startup, fall back to opening the existing store
    # in place: it already contains the previously-built embeddings.
    if os.path.exists(db_dir) and not _force_rmtree(db_dir):
        print(
            f"⚠️  Could not clear {db_dir} (locked by another process); "
            "reusing the existing index instead of rebuilding."
        )
        return Chroma(
            embedding_function=embedding_function,
            persist_directory=db_dir,
        )

    print("------------------------------------")
    print("Loading and splitting all supported files...")
    t0 = time.time()
    all_docs: list[Document] = []
    for file_path in list_supported_files():
        try:
            all_docs.extend(split_file(str(file_path)))
        except Exception as exc:
            print(f"⚠️ Skipped indexing {file_path.name}: {exc}")
    split_time = time.time() - t0
    print(f"Total chunks: {len(all_docs)}")
    print(f"Time: {split_time:.1f} sec")

    if not all_docs:
        return Chroma(
            embedding_function=embedding_function,
            persist_directory=db_dir,
        )

    print("------------------------------------")
    print("Creating embeddings and saving to Chroma...")
    t0 = time.time()
    vs = Chroma.from_documents(
        documents=all_docs,
        embedding=embedding_function,
        persist_directory=db_dir,
    )
    embed_time = time.time() - t0
    print("Done")
    print(f"Time: {embed_time:.1f} sec")
    return vs
