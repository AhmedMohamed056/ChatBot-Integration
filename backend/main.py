import os
import glob
import shutil
from pathlib import Path

from dotenv import load_dotenv

from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.document_loaders import PyMuPDFLoader
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_community.vectorstores import Chroma
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_classic.chains import create_history_aware_retriever, create_retrieval_chain
from langchain_classic.chains.combine_documents import create_stuff_documents_chain
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.messages import HumanMessage, AIMessage

load_dotenv()
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")

# ---- إعدادات المستندات ----
STATIC_PDF_DIR = "static_pdfs"
DB_DIR = "chroma_db"
os.makedirs(STATIC_PDF_DIR, exist_ok=True)

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # مؤقتًا للتجربة المحلية فقط - غيّرها لدومينك الحقيقي وقت الـ production
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---- تخزين حالة كل "session" في الذاكرة (بسيط، للتجربة) ----
# ملحوظة: في production حقيقي الأفضل تستخدم DB أو Redis بدل الـ dict العادي
sessions = {}  # session_id -> {"messages": [...]}

# ---- قاعدة المعرفة بتتبني مرة واحدة، والإضافة تتم عبر /upload ----
qa_chain = None
embeddings = None
vectordb = None


class ChatRequest(BaseModel):
    message: str
    session_id: str


class ChatResponse(BaseModel):
    reply: str


def get_embeddings():
    global embeddings
    if embeddings is None:
        embeddings = HuggingFaceEmbeddings(model_name="intfloat/multilingual-e5-base")
    return embeddings


def split_pdfs(pdf_paths: list[str]):
    documents = []
    for path in pdf_paths:
        loader = PyMuPDFLoader(path)
        documents.extend(loader.load())

    text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=150)
    return text_splitter.split_documents(documents)


def build_qa_chain_from_vectordb(db):
    retriever = db.as_retriever(search_kwargs={"k": 3})

    llm = ChatGoogleGenerativeAI(
        model="gemini-2.5-flash",
        temperature=0.0,
        google_api_key=GOOGLE_API_KEY,
        max_retries=1,
        timeout=30,
    )

    contextualize_q_system_prompt = (
        "Given a chat history and the latest user question "
        "which might reference context in the chat history, "
        "formulate a standalone question which can be understood "
        "without the chat history. Do NOT answer the question. "
        "Return ONLY the formulated standalone question and absolutely NOTHING else."
    )
    contextualize_q_prompt = ChatPromptTemplate.from_messages([
        ("system", contextualize_q_system_prompt),
        MessagesPlaceholder("chat_history"),
        ("human", "{input}"),
    ])
    history_aware_retriever = create_history_aware_retriever(
        llm, retriever, contextualize_q_prompt
    )

    system_prompt = """
You are a professional customer support assistant.

Use ONLY the retrieved context.

The user's question and the documents may be written in different languages.

IMPORTANT:
- The documents may be in English.
- The user may ask in Arabic.
- Always understand both languages.
- Use the English context to answer Arabic questions.
- Use the Arabic context to answer English questions.
- Never refuse just because the languages are different.
- If the answer truly does not exist in the context, say that it is unavailable.
- Always answer in the same language as the user's question.

Context:
{context}
"""
    qa_prompt = ChatPromptTemplate.from_messages([
        ("system", system_prompt),
        MessagesPlaceholder("chat_history"),
        ("human", "{input}"),
    ])
    question_answer_chain = create_stuff_documents_chain(llm, qa_prompt)

    return create_retrieval_chain(history_aware_retriever, question_answer_chain)


def build_rag_chain(pdf_paths: list[str]):
    global vectordb

    emb = get_embeddings()
    split_docs = split_pdfs(pdf_paths)

    if os.path.exists(DB_DIR) and os.listdir(DB_DIR):
        print("📂 Loading existing Chroma database...")
        vectordb = Chroma(
            persist_directory=DB_DIR,
            embedding_function=emb,
        )
    else:
        print("📚 Creating new Chroma database...")
        vectordb = Chroma.from_documents(
            documents=split_docs,
            embedding=emb,
            persist_directory=DB_DIR,
        )

    return build_qa_chain_from_vectordb(vectordb)


def add_pdf_to_knowledge_base(pdf_path: str):
    """Add a newly uploaded PDF into Chroma and refresh the QA chain."""
    global qa_chain, vectordb

    emb = get_embeddings()
    split_docs = split_pdfs([pdf_path])

    if not split_docs:
        raise ValueError("No text could be extracted from this PDF.")

    if vectordb is None:
        if os.path.exists(DB_DIR) and os.listdir(DB_DIR):
            vectordb = Chroma(
                persist_directory=DB_DIR,
                embedding_function=emb,
            )
            vectordb.add_documents(split_docs)
        else:
            vectordb = Chroma.from_documents(
                documents=split_docs,
                embedding=emb,
                persist_directory=DB_DIR,
            )
    else:
        vectordb.add_documents(split_docs)

    qa_chain = build_qa_chain_from_vectordb(vectordb)
    return len(split_docs)


@app.on_event("startup")
async def startup_event():
    """
    بمجرد ما السيرفر يشتغل، بيقرا كل ملفات الـ PDF الموجودة في static_pdfs
    ويبني قاعدة المعرفة مرة واحدة.
    """
    global qa_chain
    pdf_paths = glob.glob(os.path.join(STATIC_PDF_DIR, "*.pdf"))

    if not pdf_paths:
        print(f"⚠️  لا يوجد ملفات PDF في مجلد {STATIC_PDF_DIR}/ - ارفع ملفات من الموقع أو حطها في المجلد.")
        return

    print(f"📚 جاري بناء قاعدة المعرفة من {len(pdf_paths)} ملف/ملفات...")
    qa_chain = build_rag_chain(pdf_paths)
    print("✅ قاعدة المعرفة جاهزة.")


@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    if qa_chain is None:
        return ChatResponse(
            reply="عذرًا، قاعدة المعرفة مش جاهزة دلوقتي. ارفع ملف PDF من صفحة الموقع أو ضع ملفات في مجلد static_pdfs."
        )

    session = sessions.setdefault(req.session_id, {"messages": []})

    chat_history = []
    for msg in session["messages"]:
        if msg["role"] == "user":
            chat_history.append(HumanMessage(content=msg["content"]))
        else:
            chat_history.append(AIMessage(content=msg["content"]))

    try:
        response = qa_chain.invoke({
            "input": req.message,
            "chat_history": chat_history,
        })
        answer = response["answer"]
    except Exception as e:
        print(f"⚠️ خطأ من نموذج Gemini: {e}")
        answer = (
            "عذرًا، الخدمة مزحومة دلوقتي من جهة Google (النموذج تحت ضغط). "
            "جرّب تاني بعد شوية.\n"
            "Sorry, the AI service is currently overloaded on Google's side. Please try again shortly."
        )

    session["messages"].append({"role": "user", "content": req.message})
    session["messages"].append({"role": "assistant", "content": answer})

    return ChatResponse(reply=answer)


@app.get("/documents")
async def list_documents():
    files = sorted(Path(STATIC_PDF_DIR).glob("*.pdf"))
    return {
        "count": len(files),
        "files": [
            {
                "name": f.name,
                "size_kb": round(f.stat().st_size / 1024, 1),
            }
            for f in files
        ],
        "knowledge_base_ready": qa_chain is not None,
    }


@app.post("/upload")
async def upload_document(file: UploadFile = File(...)):
    filename = Path(file.filename or "").name

    if not filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported.")

    dest = Path(STATIC_PDF_DIR) / filename

    try:
        with dest.open("wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    finally:
        await file.close()

    try:
        chunks = add_pdf_to_knowledge_base(str(dest))
    except Exception as e:
        if dest.exists():
            dest.unlink()
        raise HTTPException(status_code=500, detail=f"Failed to index PDF: {e}") from e

    return {
        "ok": True,
        "filename": filename,
        "chunks_indexed": chunks,
        "message": f"Uploaded and indexed: {filename}",
    }


@app.get("/health")
async def health():
    return {"status": "running", "knowledge_base_ready": qa_chain is not None}
