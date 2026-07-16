import os
import glob
import shutil
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

from fastapi import FastAPI, File, Form, UploadFile, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
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
from langchain_core.documents import Document

load_dotenv()
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "")
ADMIN_SESSION_COOKIE = "admin_session"
ASSISTANT_NAME = "معين الزائرين"

# ---- إعدادات المستندات ----
STATIC_PDF_DIR = "static_pdfs"
DB_DIR = "chroma_db"
BACKEND_DIR = Path(__file__).resolve().parent
SUPPORTED_UPLOAD_EXTENSIONS = {".pdf", ".docx", ".txt"}
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


class LearnRequest(BaseModel):
    question: str
    answer: str
    source: str = "whatsapp_admin"


def get_supported_document_type(filename: str) -> str:
    suffix = Path(filename).suffix.lower()
    return suffix.lstrip(".").upper() if suffix in SUPPORTED_UPLOAD_EXTENSIONS else "UNKNOWN"


def get_document_status(filename: str) -> str:
    suffix = Path(filename).suffix.lower()
    if suffix == ".pdf":
        return "indexed"
    return "stored-ready-for-rag"


def list_supported_documents() -> list[dict]:
    files = []
    for path in sorted(Path(STATIC_PDF_DIR).glob("*")):
        if path.suffix.lower() not in SUPPORTED_UPLOAD_EXTENSIONS:
            continue

        files.append({
            "filename": path.name,
            "type": get_supported_document_type(path.name),
            "status": get_document_status(path.name),
            "uploaded_at": datetime.fromtimestamp(path.stat().st_mtime).isoformat(timespec="seconds"),
            "size_kb": round(path.stat().st_size / 1024, 1),
        })

    return files


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

    system_prompt = f"""
أنت {ASSISTANT_NAME}.

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
    return HTMLResponse("""
<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Admin Dashboard</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link href="https://fonts.googleapis.com/css2?family=Cairo:wght@600;700;800&family=Tajawal:wght@400;500;700&display=swap" rel="stylesheet">
  <script crossorigin src="https://unpkg.com/react@18/umd/react.development.js"></script>
  <script crossorigin src="https://unpkg.com/react-dom@18/umd/react-dom.development.js"></script>
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
      padding: 20px;
    }
    h1, h2, h3, .brand { font-family: 'Cairo', sans-serif; }
    .admin-shell {
      display: grid;
      grid-template-columns: 240px minmax(0, 1fr);
      gap: 20px;
      min-height: calc(100vh - 40px);
    }
    .sidebar {
      background: linear-gradient(155deg, var(--panel-2), var(--panel));
      border: 1px solid var(--line);
      border-radius: var(--radius);
      padding: 18px;
      display: flex;
      flex-direction: column;
      gap: 10px;
    }
    .brand {
      font-size: 20px;
      margin-bottom: 10px;
      color: var(--sand);
    }
    .nav-item {
      border: 1px solid var(--line);
      background: rgba(244,239,230,0.03);
      border-radius: 12px;
      padding: 12px 14px;
      color: var(--sand);
      cursor: pointer;
      font-weight: 700;
    }
    .nav-item.active {
      background: rgba(227,168,87,0.12);
      border-color: rgba(227,168,87,0.42);
      color: var(--gold-soft);
    }
    .main-panel {
      background: rgba(244,239,230,0.02);
      border: 1px solid var(--line);
      border-radius: var(--radius);
      padding: 24px;
    }
    .page-title {
      font-size: 28px;
      margin: 0 0 8px;
    }
    .subtext {
      color: var(--sage);
      margin: 0 0 24px;
      line-height: 1.8;
    }
    .stats-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
      gap: 18px;
      margin-bottom: 22px;
    }
    .card {
      background: linear-gradient(155deg, var(--panel-2), var(--panel));
      border: 1px solid var(--line);
      border-radius: var(--radius);
      padding: 20px;
    }
    .label {
      color: var(--sage);
      font-size: 14px;
      margin-bottom: 10px;
    }
    .value {
      font-size: 28px;
      font-family: 'Cairo', sans-serif;
      color: var(--gold-soft);
      margin-bottom: 6px;
    }
    .muted {
      color: var(--sage);
      font-size: 13px;
    }
    .charts-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
      gap: 18px;
      margin-bottom: 18px;
    }
    .bar-list {
      display: flex;
      align-items: end;
      gap: 12px;
      height: 210px;
      margin-top: 14px;
    }
    .bar-col {
      flex: 1;
      text-align: center;
    }
    .bar-body {
      display: flex;
      align-items: end;
      justify-content: center;
      height: 180px;
    }
    .bar-rail {
      width: 22px;
      border-radius: 999px;
      background: linear-gradient(180deg, var(--gold-soft), var(--gold));
      box-shadow: 0 8px 20px rgba(227,168,87,0.2);
    }
    .bar-label {
      margin-top: 8px;
      color: var(--sage);
      font-size: 12px;
    }
    .faq-list {
      list-style: none;
      margin: 6px 0 0;
      padding: 0;
      display: grid;
      gap: 10px;
    }
    .faq-item {
      display: flex;
      justify-content: space-between;
      gap: 8px;
      padding: 10px 12px;
      background: rgba(244,239,230,0.05);
      border-radius: 10px;
      border: 1px solid var(--line);
      color: var(--sand);
      font-size: 14px;
    }
    .faq-count {
      color: var(--gold-soft);
      font-weight: 700;
    }
    .upload-box {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 18px;
      margin-top: 12px;
      align-items: start;
    }
    .drop-zone {
      border: 1.5px dashed rgba(227,168,87,0.45);
      border-radius: 16px;
      padding: 24px;
      background: rgba(227,168,87,0.05);
      text-align: center;
    }
    .btn {
      padding: 12px 20px;
      border-radius: 999px;
      border: none;
      cursor: pointer;
      background: var(--gold);
      color: #1a1206;
      font-weight: 700;
      font-family: 'Tajawal', sans-serif;
      text-decoration: none;
      display: inline-block;
      margin-top: 12px;
    }
    .btn.secondary {
      background: transparent;
      color: var(--sand);
      border: 1px solid var(--line);
    }
    @media (max-width: 900px) {
      .admin-shell { grid-template-columns: 1fr; }
      .upload-box { grid-template-columns: 1fr; }
    }
  </style>
</head>
<body>
  <div id="admin-root"></div>
  <script>
    const { useState } = React;

    const stats = [
      { label: 'إجمالي المحادثات', value: '1,248', hint: '+12% هذا الأسبوع' },
      { label: 'الأسئلة المجابة', value: '934', hint: 'نسبة الإجابة 75%' },
      { label: 'الملفات المرفوعة', value: '18', hint: 'منها 6 ملفات جديدة' },
      { label: 'متوسط زمن الرد', value: '2.4s', hint: 'أقل من 3 ثوانٍ' },
    ];

    const faqData = [
      { question: 'ما هي خطوات العمرة؟', count: 184 },
      { question: 'هل يتطلب الحصول على تأشيرة؟', count: 146 },
      { question: 'ما الأماكن المهمة في مكة؟', count: 132 },
      { question: 'كيف أجد مواعيد الدخول؟', count: 127 },
    ];

    const chartData = [
      { label: 'Mon', value: 44 },
      { label: 'Tue', value: 65 },
      { label: 'Wed', value: 58 },
      { label: 'Thu', value: 73 },
      { label: 'Fri', value: 82 },
      { label: 'Sat', value: 71 },
      { label: 'Sun', value: 88 },
    ];

    function Sidebar({ active, onSelect }) {
      return React.createElement('aside', { className: 'sidebar' },
        React.createElement('div', { className: 'brand' }, 'لوحة الإدارة'),
        React.createElement('button', {
          className: `nav-item ${active === 'dashboard' ? 'active' : ''}`,
          onClick: () => onSelect('dashboard')
        }, 'Dashboard'),
        React.createElement('button', {
          className: `nav-item ${active === 'upload' ? 'active' : ''}`,
          onClick: () => onSelect('upload')
        }, 'Upload Files'),
        React.createElement('div', { style: { marginTop: 'auto' } },
          React.createElement('a', { className: 'btn secondary', href: '/admin/logout', style: { textDecoration: 'none' } }, 'تسجيل الخروج')
        )
      );
    }

    function StatCard({ label, value, hint }) {
      return React.createElement('div', { className: 'card' },
        React.createElement('div', { className: 'label' }, label),
        React.createElement('div', { className: 'value' }, value),
        React.createElement('div', { className: 'muted' }, hint)
      );
    }

    function BarChart({ data }) {
      const max = Math.max(...data.map(item => item.value));
      return React.createElement('div', { className: 'card' },
        React.createElement('div', { className: 'label' }, 'إحصائيات التفاعل الأسبوعية'),
        React.createElement('div', { className: 'bar-list' }, data.map((item) =>
          React.createElement('div', { className: 'bar-col', key: item.label },
            React.createElement('div', { className: 'bar-body' },
              React.createElement('div', {
                className: 'bar-rail',
                style: { height: `${(item.value / max) * 100}%` }
              })
            ),
            React.createElement('div', { className: 'bar-label' }, item.label)
          )
        ))
      );
    }

    function FAQPanel({ items }) {
      return React.createElement('div', { className: 'card' },
        React.createElement('div', { className: 'label' }, 'Most frequently asked questions'),
        React.createElement('ul', { className: 'faq-list' }, items.map((item) =>
          React.createElement('li', { className: 'faq-item', key: item.question },
            React.createElement('span', null, item.question),
            React.createElement('span', { className: 'faq-count' }, item.count)
          )
        ))
      );
    }

    function UploadPanel() {
      const [files, setFiles] = useState([]);
      const [dragActive, setDragActive] = useState(false);
      const [selectedFile, setSelectedFile] = useState(null);
      const [uploadMessage, setUploadMessage] = useState('');

      function loadFiles() {
        fetch('/admin/files')
          .then((res) => res.json())
          .then((data) => setFiles(data.files || []))
          .catch(() => setFiles([]));
      }

      React.useEffect(() => { loadFiles(); }, []);

      async function uploadFile(fileToUpload, replaceFilename = null) {
        if (!fileToUpload) return;

        const form = new FormData();
        form.append('file', fileToUpload);

        const url = replaceFilename ? `/admin/files/${encodeURIComponent(replaceFilename)}/replace` : '/upload';
        const method = replaceFilename ? 'POST' : 'POST';

        try {
          const res = await fetch(url, { method, body: form });
          const data = await res.json();
          setUploadMessage(data.message || 'Uploaded successfully');
          loadFiles();
        } catch (err) {
          setUploadMessage('Upload failed. Please try again.');
        }
      }

      async function deleteFile(filename) {
        try {
          const res = await fetch(`/admin/files/${encodeURIComponent(filename)}`, { method: 'DELETE' });
          const data = await res.json();
          setUploadMessage(data.message || 'Deleted successfully');
          loadFiles();
        } catch (err) {
          setUploadMessage('Delete failed.');
        }
      }

      function onDrop(e) {
        e.preventDefault();
        setDragActive(false);
        const file = e.dataTransfer.files?.[0];
        if (file) uploadFile(file);
      }

      return React.createElement('div', { className: 'card' },
        React.createElement('div', { className: 'label' }, 'Upload Files'),
        React.createElement('div', { className: 'upload-box' },
          React.createElement('div', {
            className: 'drop-zone',
            onDragOver: (e) => { e.preventDefault(); setDragActive(true); },
            onDragLeave: () => setDragActive(false),
            onDrop
          },
            React.createElement('h3', { style: { margin: '0 0 10px', fontSize: '18px' } }, 'اسحب الملف هنا أو اضغط للاختيار'),
            React.createElement('p', { style: { color: 'var(--sage)', margin: 0 } }, 'يدعم ملفات PDF و DOCX و TXT. بعد الرفع، سيتم تجهيز الملف للذكاء المعزز لاحقًا.'),
            React.createElement('label', { className: 'btn', htmlFor: 'upload-input' }, 'اختيار ملف'),
            React.createElement('input', {
              id: 'upload-input',
              type: 'file',
              accept: '.pdf,.docx,.txt',
              style: { display: 'none' },
              onChange: (e) => uploadFile(e.target.files?.[0])
            }),
            React.createElement('div', { style: { color: 'var(--gold-soft)', marginTop: '12px' } }, uploadMessage || 'جاهز للرفع')
          ),
          React.createElement('div', { className: 'card', style: { background: 'rgba(244,239,230,0.03)' } },
            React.createElement('div', { className: 'label' }, 'Uploaded files'),
            React.createElement('table', {
              style: {
                width: '100%',
                borderCollapse: 'collapse',
                color: 'var(--sand)',
                fontSize: '13px'
              }
            },
              React.createElement('thead', null,
                React.createElement('tr', null,
                  React.createElement('th', { style: { textAlign: 'right', padding: '8px 0', color: 'var(--sage)' } }, 'Name'),
                  React.createElement('th', { style: { textAlign: 'right', padding: '8px 0', color: 'var(--sage)' } }, 'Status'),
                  React.createElement('th', { style: { textAlign: 'right', padding: '8px 0', color: 'var(--sage)' } }, 'Upload date'),
                  React.createElement('th', { style: { textAlign: 'right', padding: '8px 0', color: 'var(--sage)' } }, 'Actions')
                )
              ),
              React.createElement('tbody', null,
                files.length === 0
                  ? React.createElement('tr', null,
                      React.createElement('td', { colSpan: 4, style: { padding: '12px 0', color: 'var(--sage)' } }, 'No files uploaded yet.')
                    )
                  : files.map((item) =>
                      React.createElement('tr', { key: item.filename },
                        React.createElement('td', { style: { padding: '10px 0', borderBottom: '1px solid var(--line)' } }, item.filename),
                        React.createElement('td', { style: { padding: '10px 0', borderBottom: '1px solid var(--line)' } }, item.status),
                        React.createElement('td', { style: { padding: '10px 0', borderBottom: '1px solid var(--line)' } }, item.uploaded_at),
                        React.createElement('td', { style: { padding: '10px 0', borderBottom: '1px solid var(--line)' } },
                          React.createElement('button', {
                            className: 'btn secondary',
                            style: { marginTop: 0, marginLeft: '8px', padding: '8px 12px', fontSize: '12px' },
                            onClick: () => deleteFile(item.filename)
                          }, 'Delete'),
                          React.createElement('label', {
                            className: 'btn secondary',
                            style: { marginTop: 0, padding: '8px 12px', fontSize: '12px', cursor: 'pointer' },
                            htmlFor: `replace-${item.filename}`
                          }, 'Replace'),
                          React.createElement('input', {
                            id: `replace-${item.filename}`,
                            type: 'file',
                            accept: '.pdf,.docx,.txt',
                            style: { display: 'none' },
                            onChange: (e) => {
                              const file = e.target.files?.[0];
                              if (file) uploadFile(file, item.filename);
                            }
                          })
                        )
                      )
                    )
              )
            )
          )
        )
      );
    }

    function DashboardView() {
      return React.createElement('div', null,
        React.createElement('h1', { className: 'page-title' }, 'لوحة الإدارة'),
        React.createElement('p', { className: 'subtext' }, 'مرحبًا بك في لوحة تحكم المساعد الرقمي الخاص بالعمرة في السعودية.'),
        React.createElement('div', { className: 'stats-grid' }, stats.map((item) =>
          React.createElement(StatCard, { key: item.label, ...item })
        )),
        React.createElement('div', { className: 'charts-grid' },
          React.createElement(BarChart, { data: chartData }),
          React.createElement(FAQPanel, { items: faqData })
        )
      );
    }

    function AdminApp() {
      const [activeView, setActiveView] = useState('dashboard');

      return React.createElement('div', { className: 'admin-shell' },
        React.createElement(Sidebar, { active: activeView, onSelect: setActiveView }),
        React.createElement('main', { className: 'main-panel' },
          activeView === 'dashboard'
            ? React.createElement(DashboardView)
            : React.createElement('div', null,
                React.createElement('h1', { className: 'page-title' }, 'Upload Files'),
                React.createElement('p', { className: 'subtext' }, 'استخدم هذه المنطقة لإضافة الملفات الجديدة إلى قاعدة المعرفة الخاصة بالمساعد.'),
                React.createElement(UploadPanel)
              )
        )
      );
    }

    ReactDOM.createRoot(document.getElementById('admin-root')).render(React.createElement(AdminApp));
  </script>
</body>
</html>
""")


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
    suffix = Path(filename).suffix.lower()

    if suffix not in SUPPORTED_UPLOAD_EXTENSIONS:
        raise HTTPException(status_code=400, detail="Only PDF, DOCX and TXT files are supported.")

    dest = Path(STATIC_PDF_DIR) / filename

    try:
        with dest.open("wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    finally:
        await file.close()

    if suffix == ".pdf":
        try:
            chunks = add_pdf_to_knowledge_base(str(dest))
            status = "indexed"
            message = f"Uploaded and indexed: {filename}"
        except Exception as e:
            if dest.exists():
                dest.unlink()
            raise HTTPException(status_code=500, detail=f"Failed to index PDF: {e}") from e
    else:
        status = "stored-ready-for-rag"
        chunks = 0
        message = f"Uploaded and staged for future RAG integration: {filename}"

    return {
        "ok": True,
        "filename": filename,
        "type": get_supported_document_type(filename),
        "status": status,
        "chunks_indexed": chunks,
        "uploaded_at": datetime.fromtimestamp(dest.stat().st_mtime).isoformat(timespec="seconds"),
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
    return {"ok": True, "filename": filename, "message": "File deleted"}


@app.post("/admin/files/{filename}/replace")
async def replace_admin_file(filename: str, file: UploadFile = File(...)):
    dest = Path(STATIC_PDF_DIR) / filename
    if not dest.exists():
        raise HTTPException(status_code=404, detail="File not found")

    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in SUPPORTED_UPLOAD_EXTENSIONS:
        raise HTTPException(status_code=400, detail="Only PDF, DOCX and TXT files are supported.")

    try:
        with dest.open("wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    finally:
        await file.close()

    if suffix == ".pdf":
        try:
            chunks = add_pdf_to_knowledge_base(str(dest))
            status = "indexed"
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to index replacement PDF: {e}") from e
    else:
        chunks = 0
        status = "stored-ready-for-rag"

    return {
        "ok": True,
        "filename": filename,
        "type": get_supported_document_type(filename),
        "status": status,
        "chunks_indexed": chunks,
        "uploaded_at": datetime.fromtimestamp(dest.stat().st_mtime).isoformat(timespec="seconds"),
        "message": "File replaced successfully",
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


@app.get("/health")
async def health():
    return {"status": "running", "knowledge_base_ready": qa_chain is not None}
