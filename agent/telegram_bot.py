"""
Telegram bot using FastAPI webhook server.

Local dev:   set USE_POLLING=true in .env — no tunnel needed
Cloud Run:   set WEBHOOK_URL to the Cloud Run service URL

Usage: python telegram_bot.py
Commands:
  /start  - welcome message
  /reset  - clear conversation history
"""

import os
import sys
import logging
from contextlib import asynccontextmanager
from dotenv import load_dotenv
from fastapi import FastAPI, Request, Response
import uvicorn
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from google.cloud import firestore

sys.path.insert(0, os.path.dirname(__file__))
from agent import MCPAgent

load_dotenv("../.env")

logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)

MCP_SERVERS = [
    "https://strava-mcp-86893833347.us-central1.run.app/mcp",
    "https://google-calendar-mcp-dcnbrkhvfq-uc.a.run.app/mcp",
]

MAX_MESSAGE_LENGTH = 4096
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")
PORT = int(os.getenv("PORT", "8080"))

# Firestore client reused across warm container requests
_db: firestore.AsyncClient | None = None


def get_db() -> firestore.AsyncClient:
    global _db
    if _db is None:
        _db = firestore.AsyncClient()
    return _db


async def load_messages(chat_id: int) -> list[dict]:
    doc = await get_db().collection("conversations").document(str(chat_id)).get()
    if doc.exists:
        return doc.to_dict().get("messages", [])
    return []


async def save_messages(chat_id: int, messages: list[dict]):
    await get_db().collection("conversations").document(str(chat_id)).set(
        {"messages": messages, "updated_at": firestore.SERVER_TIMESTAMP}
    )


def split_message(text: str) -> list[str]:
    if len(text) <= MAX_MESSAGE_LENGTH:
        return [text]
    chunks = []
    while text:
        chunks.append(text[:MAX_MESSAGE_LENGTH])
        text = text[MAX_MESSAGE_LENGTH:]
    return chunks


# --- Telegram handlers ---

async def start(update: Update, _context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Hey! I'm your personal running coach.\n\n"
        "I can see your Strava data and calendar to help plan your weekly runs.\n\n"
        "Try:\n"
        "• Plan my runs for this week\n"
        "• How was my training last month?\n"
        "• When do I have time to run tomorrow?\n\n"
        "/reset to start a fresh conversation."
    )


async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await save_messages(update.effective_chat.id, [])
    await update.message.reply_text("Conversation cleared. Fresh start!")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    user_text = update.message.text
    print(f"[{update.effective_user.first_name}] {user_text}")

    await context.bot.send_chat_action(chat_id, "typing")

    try:
        # New MCP connection per message — avoids event loop / anyio conflicts
        async with MCPAgent(MCP_SERVERS) as agent:
            agent._messages = await load_messages(chat_id)
            response = await agent.chat(user_text)
            await save_messages(chat_id, agent._messages)

    except Exception as e:
        print(f"[error] {e}")
        response = f"Sorry, something went wrong: {e}"

    for chunk in split_message(response):
        await update.message.reply_text(chunk)


# --- PTB application ---

def build_ptb_app() -> Application:
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("reset", reset))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    return app


# --- FastAPI webhook server ---

ptb_app: Application = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global ptb_app
    ptb_app = build_ptb_app()
    await ptb_app.initialize()
    await ptb_app.start()
    await ptb_app.bot.set_webhook(f"{WEBHOOK_URL}/telegram")
    print(f"Webhook set to {WEBHOOK_URL}/telegram")
    yield
    await ptb_app.bot.delete_webhook()
    await ptb_app.stop()
    await ptb_app.shutdown()


fastapi_app = FastAPI(lifespan=lifespan)


@fastapi_app.get("/health")
async def health():
    return {"status": "ok"}


@fastapi_app.post("/telegram")
async def telegram_webhook(request: Request):
    data = await request.json()
    update = Update.de_json(data, ptb_app.bot)
    await ptb_app.process_update(update)
    return Response(status_code=200)


# --- Entry point ---

def main():
    if not TOKEN:
        print("ERROR: TELEGRAM_BOT_TOKEN is not set")
        sys.exit(1)

    use_polling = os.getenv("USE_POLLING", "").lower() == "true"

    if use_polling:
        print("Starting in polling mode (local dev)...")
        app = build_ptb_app()
        app.run_polling()
    else:
        if not WEBHOOK_URL:
            print("ERROR: Set WEBHOOK_URL for webhook mode or USE_POLLING=true for local dev")
            sys.exit(1)
        print(f"Starting webhook server on port {PORT}...")
        uvicorn.run(fastapi_app, host="0.0.0.0", port=PORT)


if __name__ == "__main__":
    main()
