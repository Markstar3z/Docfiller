"""Entry point for Telegram form control bot."""

from __future__ import annotations

import logging
import os
from pathlib import Path

from dotenv import load_dotenv
from telegram.ext import Application

from database import Database
from handlers import BotHandlers


def setup_logging(log_file: str) -> None:
    Path(log_file).parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        handlers=[
            logging.FileHandler(log_file, encoding="utf-8"),
            logging.StreamHandler(),
        ],
    )


def main() -> None:
    load_dotenv()

    token = os.getenv("BOT_TOKEN", "").strip()
    allowed_id_raw = os.getenv("ALLOWED_USER_ID", "").strip()
    sqlite_path = os.getenv("SQLITE_PATH", "./bot_data.sqlite3").strip()
    screenshot_dir = os.getenv("SCREENSHOT_DIR", "./screenshots").strip()
    log_file = os.getenv("LOG_FILE", "./bot.log").strip()

    if not token:
        raise RuntimeError("BOT_TOKEN is missing. Set it in your .env file.")
    if not allowed_id_raw or not allowed_id_raw.isdigit():
        raise RuntimeError("ALLOWED_USER_ID must be a numeric Telegram user id in .env")

    setup_logging(log_file)
    logger = logging.getLogger(__name__)

    db = Database(sqlite_path)
    db.init()

    handlers = BotHandlers(
        allowed_user_id=int(allowed_id_raw),
        db=db,
        screenshot_dir=screenshot_dir,
    )

    app = Application.builder().token(token).build()
    handlers.callbacks_app = app
    handlers.register(app)

    async def _on_startup(application: Application) -> None:
        await handlers.start_background()
        logger.info("Bot started. Queue worker running.")

    app.post_init = _on_startup

    logger.info("Starting polling")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
