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


def rebuild_vectordb(embedding_function, db_dir: str):
    from langchain_community.vectorstores import Chroma

    if os.path.exists(db_dir):
        shutil.rmtree(db_dir)

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
