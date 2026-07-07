"""Hugging Face Spaces entrypoint for the Space News Bot."""

from __future__ import annotations

import logging
import os
import threading
import time
from datetime import datetime, timedelta

import gradio as gr

from space_news_bot import (
    fetch_telegram_updates,
    get_settings,
    load_registered_chats,
    post_news,
    process_telegram_update,
    send_telegram_message,
)


logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

_scheduler_started = False
_scheduler_lock = threading.Lock()
_listener_started = False
_listener_lock = threading.Lock()


def parse_daily_time(value: str) -> tuple[int, int]:
    hour_text, minute_text = value.split(":", 1)
    hour = max(0, min(23, int(hour_text)))
    minute = max(0, min(59, int(minute_text)))
    return hour, minute


def compute_next_run(now: datetime, hour: int, minute: int) -> datetime:
    next_run = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if next_run <= now:
        next_run += timedelta(days=1)
    return next_run


def scheduler_loop() -> None:
    settings = get_settings()
    schedule_time = os.getenv("DAILY_POST_TIME", "06:00")
    hour, minute = parse_daily_time(schedule_time)

    logger.info("Scheduler active for %02d:%02d in %s.", hour, minute, settings.timezone_name)

    while True:
        now = datetime.now(settings.timezone)
        next_run = compute_next_run(now, hour, minute)
        sleep_seconds = max(30.0, min(300.0, (next_run - now).total_seconds()))
        time.sleep(sleep_seconds)

        refreshed_now = datetime.now(settings.timezone)
        if refreshed_now >= next_run:
            logger.info("Running scheduled news post.")
            result = post_news()
            logger.info("Scheduled run finished: %s", result["message"])


def start_scheduler_once() -> None:
    global _scheduler_started

    if os.getenv("ENABLE_SCHEDULER", "true").lower() in {"0", "false", "no"}:
        logger.info("Scheduler disabled via ENABLE_SCHEDULER.")
        return

    with _scheduler_lock:
        if _scheduler_started:
            return

        thread = threading.Thread(target=scheduler_loop, daemon=True, name="space-news-scheduler")
        thread.start()
        _scheduler_started = True


def telegram_listener_loop() -> None:
    settings = get_settings()
    if not settings.telegram_bot_token:
        logger.info("Telegram listener disabled until TELEGRAM_BOT_TOKEN is configured.")
        return

    logger.info("Telegram audience listener active for chat registration.")
    offset: int | None = None
    allowed_updates = ["message", "channel_post", "my_chat_member"]

    while True:
        updates = fetch_telegram_updates(
            settings.telegram_bot_token,
            offset=offset,
            allowed_updates=allowed_updates,
        )

        for update in updates:
            update_id = update.get("update_id")
            if isinstance(update_id, int):
                offset = update_id + 1

            payload = process_telegram_update(update, settings)
            reply_chat_id = payload.get("reply_chat_id")
            reply_text = payload.get("reply_text")
            if reply_chat_id and reply_text:
                send_telegram_message(settings.telegram_bot_token, str(reply_chat_id), str(reply_text))


def start_listener_once() -> None:
    global _listener_started

    if os.getenv("ENABLE_TELEGRAM_LISTENER", "true").lower() in {"0", "false", "no"}:
        logger.info("Telegram listener disabled via ENABLE_TELEGRAM_LISTENER.")
        return

    with _listener_lock:
        if _listener_started:
            return

        thread = threading.Thread(target=telegram_listener_loop, daemon=True, name="telegram-audience-listener")
        thread.start()
        _listener_started = True


def format_status() -> str:
    settings = get_settings()
    token_status = "✅ configured" if settings.telegram_bot_token else "❌ missing"
    registered = len(load_registered_chats(settings))
    return (
        f"Telegram token     : {token_status}\n"
        f"Registered chats   : {registered}\n"
        f"Fallback channel   : {settings.channel_id}\n"
        f"Timezone           : {settings.timezone_name}\n"
        f"News limit         : {settings.news_limit}\n"
        f"Scheduler          : {os.getenv('ENABLE_SCHEDULER', 'true')}\n"
        f"Telegram listener  : {os.getenv('ENABLE_TELEGRAM_LISTENER', 'true')}\n"
        f"Daily post time    : {os.getenv('DAILY_POST_TIME', '06:00')}\n"
        f"Delivery mode      : latest digest to every registered chat + fallback channel"
    )


def send_now() -> str:
    settings = get_settings()
    stamp = datetime.now(settings.timezone).strftime("%H:%M %Z")
    result = post_news()
    icon = "✅" if result.get("ok") else "⚠️"
    return f"{icon} {result['message']}\n🕒 {stamp}"


start_scheduler_once()
start_listener_once()

with gr.Blocks(title="Space News Bot") as demo:
    gr.Markdown(
        """
        # Space News Bot

        A polished Hugging Face Space that fetches the latest space news and posts a compact digest every Ethiopian morning.

        Configure `TELEGRAM_BOT_TOKEN` and `CHANNEL_ID` in your Space secrets.
        Optional settings: `ENABLE_SCHEDULER`, `DAILY_POST_TIME`, `NEWS_LIMIT`, and `BOT_TIMEZONE`.
        """
    )

    status = gr.Textbox(label="Current configuration", value=format_status(), lines=6, interactive=False)
    output = gr.Textbox(label="Latest run result", value="Ready to send the latest digest.", lines=3, interactive=False)

    send_button = gr.Button("Send latest space news now", variant="primary")
    refresh_button = gr.Button("Refresh configuration")

    send_button.click(send_now, outputs=output)
    refresh_button.click(format_status, outputs=status)


if __name__ == "__main__":
    demo.queue()
    demo.launch(
        server_name=os.getenv("GRADIO_SERVER_NAME", "0.0.0.0"),
        server_port=int(os.getenv("PORT", os.getenv("GRADIO_SERVER_PORT", "7860"))),
        share=False,
    )