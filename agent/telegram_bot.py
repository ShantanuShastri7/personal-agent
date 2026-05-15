"""
Telegram bot interface for the running coach agent.
Uses long polling — no webhook or tunnel needed for local dev.

Usage: python telegram_bot.py
Commands:
  /start  - welcome message
  /reset  - clear conversation history
"""

import os
import sys
import logging
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
)

sys.path.insert(0, os.path.dirname(__file__))
from agent import MCPAgent

load_dotenv("../.env")

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)

MCP_SERVERS = [
    "https://strava-mcp-86893833347.us-central1.run.app/mcp",
    "https://google-calendar-mcp-dcnbrkhvfq-uc.a.run.app/mcp",
]

MAX_MESSAGE_LENGTH = 4096


def _split_message(text: str) -> list[str]:
    """Split long responses into Telegram-sized chunks."""
    if len(text) <= MAX_MESSAGE_LENGTH:
        return [text]
    chunks = []
    while text:
        chunks.append(text[:MAX_MESSAGE_LENGTH])
        text = text[MAX_MESSAGE_LENGTH:]
    return chunks


async def post_init(app: Application) -> None:
    """Open MCP connections once when the bot starts."""
    agent = MCPAgent(MCP_SERVERS)
    await agent.__aenter__()
    app.bot_data["agent"] = agent
    print(f"Connected to {len(MCP_SERVERS)} MCP servers.")
    print(f"Tools available: {[t['name'] for t in agent._tools]}")


async def post_shutdown(app: Application) -> None:
    """Close MCP connections cleanly when the bot stops."""
    agent = app.bot_data.get("agent")
    if agent:
        await agent.__aexit__(None, None, None)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Hey! I'm your personal running coach.\n\n"
        "I can see your Strava data and calendar to help you plan your weekly runs.\n\n"
        "Try asking:\n"
        "• Plan my runs for this week\n"
        "• How was my training last month?\n"
        "• When do I have time to run tomorrow?\n\n"
        "Use /reset to start a fresh conversation."
    )


async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    agent: MCPAgent = context.bot_data["agent"]
    agent.reset()
    await update.message.reply_text("Conversation cleared. Fresh start!")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    agent: MCPAgent = context.bot_data["agent"]
    user_text = update.message.text
    print(f"[message received] {update.effective_user.first_name}: {user_text}")

    await context.bot.send_chat_action(update.effective_chat.id, "typing")

    try:
        response = await agent.chat(user_text)
        print(f"[response] {response[:100]}...")
    except Exception as e:
        print(f"[error] {e}")
        response = f"Sorry, something went wrong: {e}"

    for chunk in _split_message(response):
        await update.message.reply_text(chunk)


def main():
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        print("ERROR: TELEGRAM_BOT_TOKEN is not set in .env")
        sys.exit(1)

    app = (
        Application.builder()
        .token(token)
        .post_init(post_init)
        .post_shutdown(post_shutdown)
        .build()
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("reset", reset))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("Bot is running. Press Ctrl+C to stop.")
    app.run_polling()


if __name__ == "__main__":
    main()
