# AI Customer Support Chatbot

A RAG (Retrieval-Augmented Generation) customer support system with a FastAPI backend and a WhatsApp bot integration. The backend exposes a chat API powered by Google Gemini and a Chroma vector store, plus an admin dashboard for managing documents, campaigns, and settings. The WhatsApp bot forwards group questions to the backend and replies with the AI's answers.

> **Phase 0 contract status:** the production behavior is frozen in [`docs/contracts/`](docs/contracts/) and [`docs/architecture/target-platform.md`](docs/architecture/target-platform.md). The existing SQLite, configuration-based authorization, subprocess transport, and simple admin login are legacy implementation details and are **not** production authority. Later roadmap phases must implement the contracts; do not infer compliance from the current runtime.

---

## Table of Contents

- [Project Structure](#project-structure)
- [Prerequisites](#prerequisites)
- [Environment Variables](#environment-variables)
  - [Backend `.env`](#backend-env)
  - [WhatsApp Bot `.env`](#whatsapp-bot-env)
- [Run the Backend](#run-the-backend)
- [Run the WhatsApp Bot](#run-the-whatsapp-bot)
- [Using the Bot in WhatsApp](#using-the-bot-in-whatsapp)
- [Admin Dashboard](#admin-dashboard)
- [API Reference](#api-reference)
- [Troubleshooting](#troubleshooting)

---

## Project Structure

```
ChatBot-Integration/
├── backend/                  # FastAPI RAG application (Python)
│   ├── main.py               # FastAPI app entry point
│   ├── database.py           # SQLite database helpers
│   ├── campaign_service.py   # Campaign management logic
│   ├── document_service.py   # Document loading & indexing
│   ├── date_utils.py         # Date/time context helpers
│   ├── requirements.txt      # Python dependencies
│   ├── index.html            # Public chat widget page
│   ├── admin_dashboard.html  # Admin dashboard UI
│   ├── static_pdfs/          # Uploaded knowledge-base documents
│   ├── calendar_files/       # Calendar & campaign list files
│   └── chroma_db/            # Chroma vector store (auto-created)
├── whatsapp-bot/             # WhatsApp bot integration (Node.js)
│   ├── src/
│   │   ├── index.js          # Service entry point
│   │   ├── bot.js            # WhatsApp client lifecycle
│   │   ├── config.js         # Env-based configuration
│   │   ├── ragClient.js      # Axios client for backend API
│   │   ├── handlers/         # Message handling
│   │   ├── middleware/        # Group/mention filtering
│   │   ├── services/         # Integration services
│   │   └── utils/            # Logger and shared utilities
│   ├── package.json
│   └── auth/                 # WhatsApp session data (auto-created, gitignored)
├── services/                 # Additional service helpers
└── chroma_db/                # Root-level Chroma store (if used)
```

---

## Prerequisites

- **Python 3.10+** (with `pip`)
- **Node.js 18+** (with `npm`)
- **Google Gemini API key** — get one from [Google AI Studio](https://aistudio.google.com/app/apikey)
- **Chromium/Chrome** — installed automatically by Puppeteer for the WhatsApp bot
- **WhatsApp account** — a phone with WhatsApp installed to scan the QR code on first run

---

## Environment Variables

Both services read configuration from `.env` files. These files are gitignored and must be created manually.

### Backend `.env`

Create `backend/.env`:

```env
# Google Gemini API key (required for the chat model)
GOOGLE_API_KEY=your_google_gemini_api_key_here

# Legacy development dashboard credentials (not production RBAC)
ADMIN_USERNAME=admin
ADMIN_PASSWORD=your_secure_password
```

### WhatsApp Bot `.env`

Create `whatsapp-bot/.env`:

```env
# Bot display name (used in help replies)
BOT_NAME=SupportBot

# Command prefix to trigger the bot without a mention
BOT_PREFIX=!

# Backend RAG API URL (must match the backend host:port)
RAG_API_URL=http://127.0.0.1:8000

# Winston log level: error, warn, info, debug, silly
LOG_LEVEL=info

# Axios timeout for backend requests, in milliseconds
API_TIMEOUT=60000

# Whether the bot responds in group chats
ALLOW_GROUPS=true

# Optional: comma-separated list of allowed group IDs (e.g. 120363xxx@g.us)
# Leave empty to allow all groups
ALLOWED_GROUP_IDS=

# Require the bot to be @mentioned (or use BOT_PREFIX) before replying
REQUIRE_MENTION=true

# Ignore messages sent by the bot itself
IGNORE_SELF=true

# Ignore WhatsApp status/broadcast messages
IGNORE_STATUS=true

# Number of retry attempts for failed backend requests
MAX_RETRIES=3
```

---

## Run the Backend

The backend is a FastAPI application that serves the chat API, the public chat widget, and the admin dashboard.

### 1. Create and activate a virtual environment

```bash
cd backend
python -m venv venv
```

Activate it:

- **Windows (cmd):** `venv\Scripts\activate`
- **Windows (PowerShell):** `venv\Scripts\Activate.ps1`
- **macOS/Linux:** `source venv/bin/activate`

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

> **Note (Windows):** `requirements.txt` pins `torch==2.6.0+cpu` and adds the PyTorch CPU index URL. This avoids a known `c10.dll` initialization error (`WinError 1114`) on Windows/Anaconda. If installation fails, ensure `pip` is up to date (`pip install --upgrade pip`).

### 3. Configure environment variables

Create `backend/.env` as described in [Backend `.env`](#backend-env).

### 4. (Optional) Add knowledge-base documents

Place supported files (`.pdf`, `.docx`, `.doc`, `.txt`, `.csv`, `.xlsx`) in `backend/static_pdfs/`. The backend indexes them into the Chroma vector store on startup. You can also upload files later via the admin dashboard or the `/upload` endpoint.

### 5. Start the backend

```bash
uvicorn main:app --reload
python -m http.server 5500 # to run the index page
```

The API runs on **http://127.0.0.1:8000**.

- Public chat widget: http://127.0.0.1:8000/
- Admin login: http://127.0.0.1:8000/admin/login
- Health check: http://127.0.0.1:8000/health

The current legacy backend will:

1. Initialize the SQLite database (`backend/app.db`).
2. Load and index any documents in `static_pdfs/` into the Chroma vector store (`backend/chroma_db/`).
3. Build the RAG QA chain using Google Gemini (`gemini-2.5-flash`) and HuggingFace multilingual embeddings.

The production target uses PostgreSQL as its only transactional source of truth, Redis for reconstructable queues/locks/cache, and Chroma as a reconstructable retrieval projection. Runtime supervisor authorization must come from active PostgreSQL-imported records—never configuration or Excel.

---

## Run the WhatsApp Bot

The WhatsApp bot connects to WhatsApp via `whatsapp-web.js` (a Puppeteer-based client) and forwards group questions to the backend.

### 1. Install dependencies

```bash
cd whatsapp-bot
npm install
```

> **Note:** Puppeteer downloads a compatible Chromium build during `npm install`. If it fails, run `npx puppeteer browsers install chrome` manually.

### 2. Configure environment variables

Create `whatsapp-bot/.env` as described in [WhatsApp Bot `.env`](#whatsapp-bot-env). Make sure `RAG_API_URL` points to the running backend (default: `http://127.0.0.1:8000`).

### 3. Start the bot

Development mode (auto-restart on file changes):

```bash
npm run dev
```

Production mode:

```bash
npm start
```

### 4. Scan the QR code

On first run, a QR code is printed in the terminal. Open WhatsApp on your phone → **Settings → Linked Devices → Link a Device** → scan the QR code.

After successful authentication, the session is saved in `whatsapp-bot/auth/`. Subsequent starts skip the QR code unless you log out or delete the `auth/` folder.

When you see the log line `WhatsApp client is ready.`, the bot is online.

---

## Using the Bot in WhatsApp

The production routing contract is:

- Groups are knowledge-only and can never mutate a campaign, regardless of sender role.
- Campaign management is private-chat only.
- A private non-supervisor is knowledge-only.
- A private supervisor is authorized only by an active PostgreSQL-imported record and can manage only the one-owner campaign assigned to that record.
- Admin actions require authenticated RBAC; bypass is explicit and audited.

In a group, mention the bot with an approved-knowledge question or use the configured prefix.

**Example with mention:**

```text
@SupportBot what is your return policy?
```

**Example with prefix:**

```text
! what is your return policy?
```

Group replies use approved, audience-visible knowledge only. User messages, attachments, imported cells, and retrieved text are untrusted data and cannot override authorization, source priority, or tool policy.

### Campaign updates

In private chat, the system collects a structured draft, asks only for missing contextual fields, presents a review summary, and requires the standalone token `OK`. No campaign mutation is written before that explicit confirmation. Draft/state memory persists across restarts; each commit creates immutable version and audit history. Approved campaign versions join RAG through a targeted campaign/version embedding refresh.

Ordinary deletion tombstones the campaign and removes it from active retrieval while retaining immutable history. Regulated purge is a separate, privileged, audited RBAC workflow.

---

## Admin Dashboard

The backend includes a web admin dashboard for managing the knowledge base, campaigns, and settings.

1. Go to **http://127.0.0.1:8000/admin/login**.
2. For legacy local development, log in with `ADMIN_USERNAME` and `ADMIN_PASSWORD` from `backend/.env`. Production requires authenticated users, server-side sessions, and least-privilege RBAC.
3. From the dashboard you can:
   - Upload, replace, and delete knowledge-base documents.
   - Rebuild the legacy vector store (production changes use targeted refresh).
   - Create, update, and delete campaigns.
   - View dashboard stats and reports (visitor questions, campaign activity).
   - Edit the assistant name, system prompt, and upload calendar/campaign-list files.

---

## API Reference

| Method | Endpoint                          | Description                                      |
| ------ | --------------------------------- | ------------------------------------------------ |
| GET    | `/`                               | Public chat widget page                          |
| POST   | `/chat`                           | Send a message and get an AI reply               |
| GET    | `/documents`                      | List indexed documents                           |
| POST   | `/upload`                         | Upload a document to the knowledge base         |
| POST   | `/learn`                          | Add a Q&A pair to the knowledge base             |
| POST   | `/campaign/update`                | Process a campaign update from WhatsApp          |
| GET    | `/health`                         | Health check + knowledge-base status             |
| GET    | `/admin/login`                    | Admin login page                                 |
| POST   | `/admin/login`                    | Admin login form handler                         |
| GET    | `/admin/dashboard`                | Admin dashboard (auth required)                 |
| GET    | `/admin/logout`                   | Log out of admin                                 |
| GET    | `/admin/files`                    | List uploaded files (auth required)              |
| DELETE | `/admin/files/{filename}`         | Delete a file and rebuild the index (auth)       |
| POST   | `/admin/files/{filename}/replace`  | Replace a file and rebuild the index (auth)      |
| GET    | `/admin/stats`                    | Dashboard statistics (auth required)             |
| GET    | `/admin/campaigns`                | List campaigns (auth required)                   |
| POST   | `/admin/campaigns`                | Create a campaign (auth required)                |
| PUT    | `/admin/campaigns/{id}`           | Update a campaign (auth required)                |
| DELETE | `/admin/campaigns/{id}`           | Delete a campaign (auth required)                |
| GET    | `/admin/reports/campaign-activity`| Campaign activity report (auth required)          |
| GET    | `/admin/reports/visitor-questions`| Visitor questions report (auth required)         |
| GET    | `/admin/settings`                 | Get settings (auth required)                     |
| PUT    | `/admin/settings`                 | Update settings (auth required)                 |
| POST   | `/admin/settings/calendar`        | Upload a calendar file (auth required)          |
| POST   | `/admin/settings/campaign-list`   | Upload a campaign-list file (auth required)     |

### `/chat` request body

```json
{
  "message": "What is your return policy?",
  "session_id": "user-123",
  "source": "website"
}
```

`source` can be `website` or `whatsapp`.

All relative-date behavior uses the trusted system date/time and configured IANA business timezone (`Asia/Riyadh` initially). Authoritative source order, prompt-injection boundaries, deletion/purge behavior, and complete lifecycle semantics are defined in [`docs/contracts/`](docs/contracts/).

---

## Troubleshooting

### Backend

- **`GOOGLE_API_KEY is not configured`** — The `.env` file is missing or the key is empty. Make sure `backend/.env` exists and `load_dotenv()` can find it (run `uvicorn` from the `backend/` directory).
- **`c10.dll` / `WinError 1114` on Windows** — Keep the pinned `torch==2.6.0+cpu` in `requirements.txt` and install from a clean virtual environment.
- **`No supported files in static_pdfs/`** — The backend starts but the QA chain is not built. Upload a document via the admin dashboard or place a file in `static_pdfs/` and restart.
- **Gemini overload errors** — The backend returns a friendly Arabic/English overload message. Wait and retry.

### WhatsApp Bot

- **`Missing required environment variable: ...`** — A required key is missing from `whatsapp-bot/.env`. Check [WhatsApp Bot `.env`](#whatsapp-bot-env).
- **QR code not appearing** — Make sure the terminal supports UTF-8. Run the bot in a normal terminal (not a piped output).
- **Chrome not found** — Run `npx puppeteer browsers install chrome` inside `whatsapp-bot/`.
- **Bot not replying in a group** — Verify:
  - `ALLOW_GROUPS=true`
  - `REQUIRE_MENTION=true` and the bot is @mentioned, or the message starts with `BOT_PREFIX`
  - `ALLOWED_GROUP_IDS` is empty (allow all) or includes the group ID
  - The backend is running and `RAG_API_URL` is correct
- **Session expired** — Delete the `whatsapp-bot/auth/` folder and restart to scan a new QR code.