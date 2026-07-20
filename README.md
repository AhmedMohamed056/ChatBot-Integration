# AI Customer Support Chatbot

Project Structure

/backend

Contains the existing FastAPI RAG application.

/whatsapp-bot

WhatsApp integration that replies in groups when the bot is mentioned.

## Run the project

### 1. Start the backend

```webpage
cd backend
python -m http.server 5500
```

```bash
cd backend
uvicorn main:app --reload
```

The API runs on `http://127.0.0.1:8000`.

### 2. Start the WhatsApp bot

```bash
cd whatsapp-bot
npm install
npm run dev
```

Scan the QR code on first run. After that, the session is saved in `whatsapp-bot/auth/`.

### 3. Use it in a WhatsApp group

1. Add the bot account to a group.
2. Mention the bot in a message with your question.

Example:

```text
@SupportBot what is your return policy?
```

The bot only replies in groups when it is mentioned.
