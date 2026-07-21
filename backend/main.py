import os
import shutil
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

from fastapi import FastAPI, File, Form, UploadFile, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from pydantic import BaseModel

from langchain_huggingface import HuggingFaceEmbeddings
from langchain_community.vectorstores import Chroma
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_classic.chains import create_history_aware_retriever, create_retrieval_chain
from langchain_classic.chains.combine_documents import create_stuff_documents_chain
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.messages import HumanMessage, AIMessage
from langchain_core.documents import Document

from campaign_service import build_active_campaign_context, process_campaign_update
from database import (
    add_visitor_question,
    create_campaign,
    delete_campaign,
    delete_uploaded_file_record,
    get_all_settings,
    get_campaign_activity_report,
    get_dashboard_stats,
    get_top_visitor_questions,
    get_unanswered_questions,
    init_db,
    list_campaigns,
    list_uploaded_files_db,
    set_setting,
    update_campaign,
    upsert_uploaded_file,
)
from date_utils import format_datetime_context_block
from document_service import (
    SUPPORTED_UPLOAD_EXTENSIONS,
    get_supported_document_type,
    list_supported_files,
    rebuild_vectordb,
    split_file,
)

load_dotenv()
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "")
ADMIN_SESSION_COOKIE = "admin_session"

# ---- إعدادات المستندات ----
STATIC_PDF_DIR = "static_pdfs"
DB_DIR = "chroma_db"
CALENDAR_DIR = "calendar_files"
BACKEND_DIR = Path(__file__).resolve().parent
os.makedirs(STATIC_PDF_DIR, exist_ok=True)
os.makedirs(CALENDAR_DIR, exist_ok=True)

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
    source: str = "website"


class ChatResponse(BaseModel):
    reply: str


class LearnRequest(BaseModel):
    question: str
    answer: str
    source: str = "whatsapp_admin"


class CampaignRequest(BaseModel):
    name: str
    whatsapp_number: str
    status: str = "active"


class CampaignUpdateRequest(BaseModel):
    phone: str
    message: str


class SettingsUpdateRequest(BaseModel):
    assistant_name: str | None = None
    system_prompt: str | None = None
    campaign_list_file: str | None = None


def list_supported_documents() -> list[dict]:
    db_files = {item["filename"]: item for item in list_uploaded_files_db()}
    files = []

    for path in list_supported_files():
        db_row = db_files.get(path.name)
        uploaded_at = db_row["uploaded_at"] if db_row else datetime.fromtimestamp(
            path.stat().st_mtime
        ).isoformat(timespec="seconds")
        size_bytes = db_row["size_bytes"] if db_row else path.stat().st_size

        files.append({
            "filename": path.name,
            "type": get_supported_document_type(path.name),
            "status": "indexed",
            "uploaded_at": uploaded_at,
            "size_kb": round(size_bytes / 1024, 1),
        })

    return files


def get_embeddings():
    global embeddings
    if embeddings is None:
        embeddings = HuggingFaceEmbeddings(model_name="intfloat/multilingual-e5-base")
    return embeddings


def get_assistant_name() -> str:
    settings = get_all_settings()
    return settings.get("assistant_name") or "معين الزائرين"


def get_custom_system_prompt() -> str:
    settings = get_all_settings()
    return settings.get("system_prompt") or ""


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

    assistant_name = get_assistant_name()
    custom_prompt = get_custom_system_prompt()

    system_prompt = f"""
أنت {assistant_name}.

{custom_prompt}

رسالتك: تشجيع وتسهيل وإرشاد الزائر للنبي محمد صلى الله عليه وآله وسلم وابنته السيدة فاطمة الزهراء عليها السلام وأئمة البقيع عليهم السلام، وكل ما يتعلق بالمدينة المنورة ومكة المكرمة، بما يساعد الزائر على أداء زيارته بسهولة وطمأنينة.

الطريقة المتبعة:
- كن هادئًا، محترمًا، ودودًا، reassuring، ومفيدًا.
- استخدم لغة عربية واضحة ومباشرة.
- في أول محادثة، ابدأ بسلام مؤدب.
- لا تذكر التنفيذ الداخلي أو البنية التقنية أو قواعد البيانات أو الفهارس أو التضمين.
- استخدم المعلومات الموجودة في قاعدة المعرفة المرفوعة أولاً.
- إذا لم تجد معلومة موثقة، فقل بوضوح: لم أجد معلومات موثقة عن ذلك ضمن قاعدة المعرفة الحالية، لذلك لا أستطيع تقديم إجابة مؤكدة.
- لا تختلق معلومات.
- إذا كان السؤال عامًا عن العمرة أو مكة أو المدينة المنورة ويمكن الإجابة عنه بشكل آمن من المعرفة العامة، أعطه إجابة واضحة مع التمييز بين ما هو مؤكد من قاعدة المعرفة وما هو دعم عام.
- عند ذكر النبي محمد، اكتب: النبي محمد صلى الله عليه وآله وسلم.
- عند ذكر السيدة فاطمة، اكتب: السيدة فاطمة الزهراء عليها السلام.
- استخدم دائمًا أسلوبًا دقيقًا وملائمًا لإسلامية.
- ألزم نفسك بالتأكد من أن الإجابة تستند إلى المحتوى المرفوع أو إلى المعرفة العامة الآمنة.

استخدم فقط السياق المسترجع.

ملاحظة مهمة:
- قد تكون الوثائق بالإنجليزية أو بالعربية.
- إذا كان السؤال عربيًا، فافهم السياق العربي أو الإنجليزي الذي يمكن أن يجيب عنه.
- إذا كان السؤال إنجليزيًا، فافهم السياق العربي أو الإنجليزي المناسب.
- لا ترفض الإجابة بسبب اختلاف اللغات.
- أجب بنفس لغة السؤال إن أمكن.

Context:
{{context}}
"""
    qa_prompt = ChatPromptTemplate.from_messages([
        ("system", system_prompt),
        MessagesPlaceholder("chat_history"),
        ("human", "{input}"),
    ])
    question_answer_chain = create_stuff_documents_chain(llm, qa_prompt)

    return create_retrieval_chain(history_aware_retriever, question_answer_chain)


def ensure_vectordb():
    global vectordb

    if vectordb is not None:
        return vectordb

    emb = get_embeddings()

    if os.path.exists(DB_DIR) and os.listdir(DB_DIR):
        print("📂 Loading existing Chroma database...")
        vectordb = Chroma(
            persist_directory=DB_DIR,
            embedding_function=emb,
        )
    else:
        print("📚 Creating new Chroma database...")
        vectordb = Chroma(
            embedding_function=emb,
            persist_directory=DB_DIR,
        )

    return vectordb


def refresh_qa_chain():
    global qa_chain, vectordb

    emb = get_embeddings()
    vectordb = rebuild_vectordb(emb, DB_DIR)
    qa_chain = build_qa_chain_from_vectordb(vectordb)
    return qa_chain


def add_text_to_knowledge_base(question: str, answer: str, source: str = "whatsapp_admin"):
    global qa_chain

    db = ensure_vectordb()
    question = question.strip()
    answer = answer.strip()

    if not question or not answer:
        raise ValueError("Question and answer are required.")

    learn_doc = Document(
        page_content=f"Question: {question}\nAnswer: {answer}",
        metadata={
            "source": source,
            "type": "whatsapp_admin",
            "question": question,
        },
    )

    db.add_documents([learn_doc])
    qa_chain = build_qa_chain_from_vectordb(db)
    return 1


def add_document_to_knowledge_base(file_path: str):
    """Add a newly uploaded document into Chroma and refresh the QA chain."""
    global qa_chain, vectordb

    split_docs = split_file(file_path)
    if not split_docs:
        raise ValueError("No text could be extracted from this file.")

    emb = get_embeddings()
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


def rebuild_knowledge_base():
    global qa_chain, vectordb
    qa_chain = refresh_qa_chain()
    return qa_chain is not None


def is_admin_authenticated(request: Request) -> bool:
    return request.cookies.get(ADMIN_SESSION_COOKIE) == "authenticated"


@app.middleware("http")
async def admin_route_guard(request: Request, call_next):
    if request.url.path == "/admin":
        return RedirectResponse(url="/admin/login", status_code=307)

    if request.url.path.startswith("/admin/") and request.url.path not in {"/admin/login", "/admin/logout"}:
        if not is_admin_authenticated(request):
            return RedirectResponse(url="/admin/login", status_code=307)

    return await call_next(request)


def render_admin_login_page() -> HTMLResponse:
    return HTMLResponse("""
<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Admin Login</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link href="https://fonts.googleapis.com/css2?family=Cairo:wght@600;700;800&family=Tajawal:wght@400;500;700&display=swap" rel="stylesheet">
  <style>
    :root{
      --ink: #0E2B2C;
      --panel: #133B3B;
      --panel-2: #16474A;
      --gold: #E3A857;
      --gold-soft: #F0C685;
      --sand: #F4EFE6;
      --sage: #9FB8B3;
      --line: rgba(244,239,230,0.10);
      --radius: 18px;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      min-height: 100vh;
      background: radial-gradient(1100px 600px at 85% -10%, rgba(227,168,87,0.18), transparent 60%), radial-gradient(900px 500px at -10% 110%, rgba(227,168,87,0.10), transparent 60%), var(--ink);
      color: var(--sand);
      font-family: 'Tajawal', sans-serif;
      display: flex;
      align-items: center;
      justify-content: center;
      padding: 24px;
    }
    .card {
      width: min(460px, 100%);
      background: linear-gradient(155deg, var(--panel-2), var(--panel));
      border: 1px solid var(--line);
      border-radius: var(--radius);
      box-shadow: 0 30px 60px -20px rgba(0,0,0,0.55);
      padding: 28px;
    }
    h1, .brand { font-family: 'Cairo', sans-serif; }
    h1 { margin: 0 0 10px; font-size: 28px; }
    p { color: var(--sage); margin: 0 0 20px; line-height: 1.8; }
    form { display: grid; gap: 14px; }
    label { font-size: 14px; color: var(--sand); display: grid; gap: 8px; }
    input {
      width: 100%;
      border-radius: 12px;
      border: 1px solid var(--line);
      background: rgba(244,239,230,0.06);
      padding: 12px 14px;
      color: var(--sand);
      font-family: 'Tajawal', sans-serif;
      font-size: 15px;
    }
    input:focus { outline: none; border-color: var(--gold-soft); }
    .btn {
      padding: 14px 26px;
      border-radius: 999px;
      font-weight: 700;
      font-size: 15px;
      border: none;
      cursor:pointer;
      background: var(--gold);
      color: #1a1206;
    }
  </style>
</head>
<body>
  <div class="card">
    <div class="brand" style="margin-bottom: 12px;">Admin Access</div>
    <h1>تسجيل الدخول للإدارة</h1>
    <p>استخدم اسم المستخدم وكلمة المرور الخاصة بالإدارة للدخول إلى لوحة التحكم.</p>
    <form method="post" action="/admin/login">
      <label>
        اسم المستخدم
        <input name="username" type="text" required />
      </label>
      <label>
        كلمة المرور
        <input name="password" type="password" required />
      </label>
      <button class="btn" type="submit">دخول</button>
    </form>
  </div>
</body>
</html>
""")


def render_admin_dashboard() -> HTMLResponse:
    dashboard_path = BACKEND_DIR / "admin_dashboard.html"
    return HTMLResponse(dashboard_path.read_text(encoding="utf-8"))


@app.get("/")
async def home_page():
    return FileResponse(BACKEND_DIR / "index.html")


@app.get("/admin")
async def admin_root_redirect():
    return RedirectResponse(url="/admin/login", status_code=307)


@app.get("/admin/login")
async def admin_login_page(request: Request):
    if is_admin_authenticated(request):
        return RedirectResponse(url="/admin/dashboard", status_code=307)
    return render_admin_login_page()


@app.post("/admin/login")
async def admin_login_submit(username: str = Form(...), password: str = Form(...)):
    if not ADMIN_USERNAME or not ADMIN_PASSWORD:
        raise HTTPException(status_code=503, detail="Admin credentials are not configured in the environment")

    if username != ADMIN_USERNAME or password != ADMIN_PASSWORD:
        raise HTTPException(status_code=401, detail="Invalid admin credentials")

    response = RedirectResponse(url="/admin/dashboard", status_code=303)
    response.set_cookie(
        key=ADMIN_SESSION_COOKIE,
        value="authenticated",
        httponly=True,
        samesite="lax",
        max_age=3600,
        path="/",
    )
    return response


@app.get("/admin/dashboard")
async def admin_dashboard(request: Request):
    if not is_admin_authenticated(request):
        return RedirectResponse(url="/admin/login", status_code=307)
    return render_admin_dashboard()


@app.get("/admin/logout")
async def admin_logout():
    response = RedirectResponse(url="/admin/login", status_code=303)
    response.delete_cookie(key=ADMIN_SESSION_COOKIE, path="/")
    return response


@app.on_event("startup")
async def startup_event():
    """Initialize SQLite and build the knowledge base from uploaded files."""
    global qa_chain

    init_db()
    supported_files = list_supported_files()

    if not supported_files:
        print(f"⚠️  No supported files in {STATIC_PDF_DIR}/ yet.")
        return

    print(f"📚 Building knowledge base from {len(supported_files)} file(s)...")
    for file_path in supported_files:
        upsert_uploaded_file(
            filename=file_path.name,
            file_type=get_supported_document_type(file_path.name),
            size_bytes=file_path.stat().st_size,
            file_path=str(file_path),
            uploaded_at=datetime.fromtimestamp(file_path.stat().st_mtime).isoformat(timespec="seconds"),
        )
    qa_chain = refresh_qa_chain()
    print("✅ Knowledge base ready.")


def build_enriched_question(message: str) -> str:
    campaign_context = build_active_campaign_context()
    datetime_context = format_datetime_context_block()
    return (
        f"{datetime_context}\n\n"
        f"Active Campaign Information (not part of RAG, use only if relevant and not expired):\n"
        f"{campaign_context}\n\n"
        f"Visitor Question:\n{message}"
    )


def looks_like_successful_answer(answer: str) -> bool:
    failure_markers = [
        "لم أجد معلومات موثقة",
        "لا أستطيع تقديم إجابة مؤكدة",
        "عذرًا، قاعدة المعرفة",
        "Sorry, the AI service is currently overloaded",
    ]
    return not any(marker in answer for marker in failure_markers)


@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    if qa_chain is None:
        add_visitor_question(req.message, answered=False, session_id=req.session_id, source=req.source)
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

    enriched_input = build_enriched_question(req.message)

    try:
        response = qa_chain.invoke({
            "input": enriched_input,
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

    add_visitor_question(
        req.message,
        answered=looks_like_successful_answer(answer),
        session_id=req.session_id,
        source=req.source,
    )

    session["messages"].append({"role": "user", "content": req.message})
    session["messages"].append({"role": "assistant", "content": answer})

    return ChatResponse(reply=answer)


@app.get("/documents")
async def list_documents():
    files = list_supported_files()
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


def save_uploaded_file(file: UploadFile, dest: Path) -> None:
    with dest.open("wb") as buffer:
        shutil.copyfileobj(file.file, buffer)


@app.post("/upload")
async def upload_document(file: UploadFile = File(...)):
    filename = Path(file.filename or "").name
    suffix = Path(filename).suffix.lower()

    if suffix not in SUPPORTED_UPLOAD_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail="Supported file types: PDF, DOCX, DOC, TXT, CSV, XLSX.",
        )

    dest = Path(STATIC_PDF_DIR) / filename

    try:
        save_uploaded_file(file, dest)
    finally:
        await file.close()

    try:
        chunks = add_document_to_knowledge_base(str(dest))
        status = "indexed"
        message = f"Uploaded and indexed: {filename}"
    except Exception as e:
        if dest.exists():
            dest.unlink()
        raise HTTPException(status_code=500, detail=f"Failed to index file: {e}") from e

    uploaded_at = datetime.fromtimestamp(dest.stat().st_mtime).isoformat(timespec="seconds")
    upsert_uploaded_file(
        filename=filename,
        file_type=get_supported_document_type(filename),
        size_bytes=dest.stat().st_size,
        file_path=str(dest),
        uploaded_at=uploaded_at,
    )

    return {
        "ok": True,
        "filename": filename,
        "type": get_supported_document_type(filename),
        "status": status,
        "chunks_indexed": chunks,
        "uploaded_at": uploaded_at,
        "message": message,
    }


@app.get("/admin/files")
async def admin_uploaded_files():
    return {"files": list_supported_documents()}


@app.delete("/admin/files/{filename}")
async def delete_admin_file(filename: str):
    dest = Path(STATIC_PDF_DIR) / filename
    if not dest.exists():
        raise HTTPException(status_code=404, detail="File not found")

    dest.unlink()
    delete_uploaded_file_record(filename)
    rebuild_knowledge_base()
    return {"ok": True, "filename": filename, "message": "File deleted and knowledge base rebuilt"}


@app.post("/admin/files/{filename}/replace")
async def replace_admin_file(filename: str, file: UploadFile = File(...)):
    dest = Path(STATIC_PDF_DIR) / filename
    if not dest.exists():
        raise HTTPException(status_code=404, detail="File not found")

    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in SUPPORTED_UPLOAD_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail="Supported file types: PDF, DOCX, DOC, TXT, CSV, XLSX.",
        )

    try:
        save_uploaded_file(file, dest)
    finally:
        await file.close()

    try:
        rebuild_knowledge_base()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to rebuild knowledge base: {e}") from e

    uploaded_at = datetime.fromtimestamp(dest.stat().st_mtime).isoformat(timespec="seconds")
    upsert_uploaded_file(
        filename=filename,
        file_type=get_supported_document_type(filename),
        size_bytes=dest.stat().st_size,
        file_path=str(dest),
        uploaded_at=uploaded_at,
    )

    return {
        "ok": True,
        "filename": filename,
        "type": get_supported_document_type(filename),
        "status": "indexed",
        "uploaded_at": uploaded_at,
        "message": "File replaced and knowledge base rebuilt",
    }


@app.post("/learn")
async def learn_from_whatsapp(req: LearnRequest):
    if not req.question.strip() or not req.answer.strip():
        raise HTTPException(status_code=400, detail="Question and answer are required.")

    try:
        chunks = add_text_to_knowledge_base(req.question, req.answer, source=req.source)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to add knowledge: {e}") from e

    return {
        "ok": True,
        "chunks_indexed": chunks,
        "message": "Knowledge added to the bot's retrieval index.",
    }


@app.post("/campaign/update")
async def campaign_update(req: CampaignUpdateRequest):
    if not GOOGLE_API_KEY:
        raise HTTPException(status_code=503, detail="GOOGLE_API_KEY is not configured")

    result = process_campaign_update(req.phone, req.message, GOOGLE_API_KEY)
    if not result.get("ok"):
        raise HTTPException(status_code=404, detail=result.get("reason", "Campaign not found"))

    return result


@app.get("/admin/stats")
async def admin_stats():
    return get_dashboard_stats()


@app.get("/admin/campaigns")
async def admin_list_campaigns():
    return {"campaigns": list_campaigns()}


@app.post("/admin/campaigns")
async def admin_create_campaign(req: CampaignRequest):
    try:
        campaign = create_campaign(req.name, req.whatsapp_number, req.status)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return {"ok": True, "campaign": campaign}


@app.put("/admin/campaigns/{campaign_id}")
async def admin_update_campaign(campaign_id: int, req: CampaignRequest):
    campaign = update_campaign(campaign_id, req.name, req.whatsapp_number, req.status)
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    return {"ok": True, "campaign": campaign}


@app.delete("/admin/campaigns/{campaign_id}")
async def admin_delete_campaign(campaign_id: int):
    deleted = delete_campaign(campaign_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Campaign not found")
    return {"ok": True, "message": "Campaign deleted"}


@app.get("/admin/reports/campaign-activity")
async def admin_campaign_activity_report():
    return {"items": get_campaign_activity_report()}


@app.get("/admin/reports/visitor-questions")
async def admin_visitor_questions_report():
    return {
        "top_questions": get_top_visitor_questions(),
        "unanswered": get_unanswered_questions(),
    }


@app.get("/admin/settings")
async def admin_get_settings():
    return get_all_settings()


@app.put("/admin/settings")
async def admin_update_settings(req: SettingsUpdateRequest):
    if req.assistant_name is not None:
        set_setting("assistant_name", req.assistant_name)
    if req.system_prompt is not None:
        set_setting("system_prompt", req.system_prompt)
    if req.campaign_list_file is not None:
        set_setting("campaign_list_file", req.campaign_list_file)

    global qa_chain
    if qa_chain is not None:
        qa_chain = build_qa_chain_from_vectordb(vectordb)

    return {"ok": True, "settings": get_all_settings()}


@app.post("/admin/settings/calendar")
async def admin_upload_calendar(file: UploadFile = File(...)):
    filename = Path(file.filename or "calendar.json").name
    dest = Path(CALENDAR_DIR) / filename

    try:
        save_uploaded_file(file, dest)
    finally:
        await file.close()

    set_setting("calendar_file", str(dest))
    return {
        "ok": True,
        "calendar_file": str(dest),
        "message": "Calendar file uploaded successfully",
    }


@app.post("/admin/settings/campaign-list")
async def admin_upload_campaign_list(file: UploadFile = File(...)):
    filename = Path(file.filename or "campaign_list.json").name
    dest = Path(CALENDAR_DIR) / filename

    try:
        save_uploaded_file(file, dest)
    finally:
        await file.close()

    set_setting("campaign_list_file", str(dest))
    return {
        "ok": True,
        "campaign_list_file": str(dest),
        "message": "Campaign list file uploaded successfully",
    }


@app.get("/health")
async def health():
    return {"status": "running", "knowledge_base_ready": qa_chain is not None}
