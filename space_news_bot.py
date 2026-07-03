"""Core logic for fetching and posting space news to Telegram.

The module is import-safe so it can be used both from a one-shot runner and from
the Hugging Face Space app entrypoint.
"""

from __future__ import annotations

import html
import json
import logging
import os
import threading
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import pytz
import requests
from dotenv import load_dotenv


logger = logging.getLogger(__name__)

DEFAULT_API_URL = "https://api.spaceflightnewsapi.net/v4/articles/"
DEFAULT_LIMIT = 5
DEFAULT_TIMEZONE = "Africa/Addis_Ababa"
DEFAULT_CHANNEL = "@channel_of_ermi"
DEFAULT_REGISTRY_FILE = "telegram_targets.json"
DEFAULT_LISTENER_TIMEOUT = 50
MAX_ARTICLES_PER_MESSAGE = 5

_registry_lock = threading.Lock()

load_dotenv(dotenv_path=".env", override=True)


@dataclass(frozen=True)
class BotSettings:
    telegram_bot_token: str | None
    channel_id: str
    timezone_name: str
    news_limit: int
    api_url: str
    registry_path: str

    @property
    def timezone(self):
        return pytz.timezone(self.timezone_name)


def get_settings() -> BotSettings:
    """Collect runtime settings from environment variables."""

    try:
        news_limit = max(1, int(os.getenv("NEWS_LIMIT", str(DEFAULT_LIMIT))))
    except ValueError:
        news_limit = DEFAULT_LIMIT

    return BotSettings(
        telegram_bot_token=os.getenv("TELEGRAM_BOT_TOKEN"),
        channel_id=os.getenv("CHANNEL_ID", DEFAULT_CHANNEL),
        timezone_name=os.getenv("BOT_TIMEZONE", DEFAULT_TIMEZONE),
        news_limit=news_limit,
        api_url=os.getenv("SPACE_NEWS_API_URL", DEFAULT_API_URL),
        registry_path=os.getenv("TELEGRAM_TARGETS_FILE", DEFAULT_REGISTRY_FILE),
    )


def _registry_file(settings: BotSettings | None = None) -> Path:
    runtime_settings = settings or get_settings()
    return Path(runtime_settings.registry_path)


def load_registered_chats(settings: BotSettings | None = None) -> list[dict[str, Any]]:
    """Load known Telegram destinations from the registry file."""

    registry_file = _registry_file(settings)
    if not registry_file.exists():
        return []

    try:
        with registry_file.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Could not read Telegram registry %s: %s", registry_file, exc)
        return []

    if not isinstance(data, list):
        return []

    chats: list[dict[str, Any]] = []
    for record in data:
        if isinstance(record, dict) and record.get("chat_id") is not None:
            chats.append(record)
    return chats


def save_registered_chats(chats: list[dict[str, Any]], settings: BotSettings | None = None) -> None:
    """Persist Telegram destinations atomically."""

    registry_file = _registry_file(settings)
    registry_file.parent.mkdir(parents=True, exist_ok=True)
    temp_file = registry_file.with_suffix(f"{registry_file.suffix}.tmp")

    with temp_file.open("w", encoding="utf-8") as handle:
        json.dump(chats, handle, indent=2, ensure_ascii=False)

    temp_file.replace(registry_file)


def _normalized_chat_name(chat: dict[str, Any]) -> str:
    title = chat.get("title")
    if title:
        return str(title)

    parts = [chat.get("first_name"), chat.get("last_name")]
    display_name = " ".join(str(part) for part in parts if part)
    return display_name or str(chat.get("username") or chat.get("id") or "Unknown chat")


def upsert_registered_chat(chat: dict[str, Any], settings: BotSettings | None = None) -> bool:
    """Add or refresh a chat in the registry."""

    chat_id = chat.get("id")
    if chat_id is None:
        return False

    runtime_settings = settings or get_settings()
    chat_id_text = str(chat_id)
    record = {
        "chat_id": chat_id_text,
        "chat_type": chat.get("type", "unknown"),
        "title": _normalized_chat_name(chat),
        "username": chat.get("username"),
        "registered_at": datetime.utcnow().isoformat() + "Z",
    }

    with _registry_lock:
        chats = load_registered_chats(runtime_settings)
        for index, existing in enumerate(chats):
            if str(existing.get("chat_id")) == chat_id_text:
                chats[index] = {**existing, **record}
                break
        else:
            chats.append(record)

        save_registered_chats(chats, runtime_settings)

    return True


def collect_delivery_targets(settings: BotSettings | None = None) -> list[dict[str, Any]]:
    """Return all known Telegram destinations, including the configured fallback channel."""

    runtime_settings = settings or get_settings()
    targets = load_registered_chats(runtime_settings)

    if runtime_settings.channel_id:
        targets.append(
            {
                "chat_id": runtime_settings.channel_id,
                "chat_type": "configured_channel",
                "title": runtime_settings.channel_id,
                "username": runtime_settings.channel_id,
            }
        )

    deduped: list[dict[str, Any]] = []
    seen: set[str] = set()
    for target in targets:
        chat_id_text = str(target.get("chat_id", "")).strip()
        if not chat_id_text or chat_id_text in seen:
            continue
        seen.add(chat_id_text)
        deduped.append(target)

    return deduped


def fetch_latest_space_news(limit: int | None = None, timezone_name: str | None = None) -> list[dict[str, Any]]:
    """Fetch the latest space news articles from the Spaceflight News API."""

    settings = get_settings()
    api_limit = limit or settings.news_limit

    try:
        response = requests.get(
            settings.api_url,
            params={"limit": api_limit},
            timeout=20,
        )
        response.raise_for_status()
        data = response.json()

        results = data.get("results", [])

        latest_articles = []
        seen_keys: set[str] = set()
        for article in results:
            published_at = article.get("published_at")
            if not published_at:
                continue

            article_key = article.get("url") or article.get("title") or published_at
            if article_key in seen_keys:
                continue
            seen_keys.add(article_key)
            latest_articles.append(article)

        latest_articles.sort(key=lambda article: article.get("published_at", ""), reverse=True)
        limited_articles = latest_articles[:api_limit]
        logger.info("Found %s latest article(s).", len(limited_articles))
        return limited_articles

    except requests.RequestException as exc:
        logger.error("API error while fetching space news: %s", exc)
        return []
    except Exception as exc:
        logger.error("Unexpected error while fetching space news: %s", exc)
        return []


def send_telegram_message(token: str, chat_id: str, text: str) -> bool:
    """Send a Telegram message using the HTTP Bot API."""

    endpoint = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }

    try:
        response = requests.post(endpoint, json=payload, timeout=20)
        response.raise_for_status()
        response_data = response.json()
        if not response_data.get("ok", False):
            logger.error("Telegram API returned an error: %s", response_data)
            return False
        return True
    except requests.RequestException as exc:
        logger.error("Telegram request failed: %s", exc)
        return False
    except ValueError as exc:
        logger.error("Telegram response could not be parsed: %s", exc)
        return False


def _escape_message_value(value: Any) -> str:
    return html.escape(str(value), quote=False)


def _escape_message_attribute(value: Any) -> str:
    return html.escape(str(value), quote=True)


def _truncate_text(value: Any, max_length: int = 240) -> str:
    text = str(value).strip()
    if len(text) <= max_length:
        return text
    return text[: max_length - 1].rstrip() + "…"


def format_article_digest(articles: list[dict[str, Any]], timezone_name: str) -> str:
    """Format a compact Telegram digest for one or more articles."""

    timezone = pytz.timezone(timezone_name)
    lines = [
        "<b>Latest Space News</b>",
        f"<i>{_escape_message_value(datetime.now(timezone).strftime('%a, %d %b %Y'))}</i>",
        "",
    ]

    for index, article in enumerate(articles[:MAX_ARTICLES_PER_MESSAGE], start=1):
        title = _escape_message_value(article.get("title", "Untitled article"))
        url = _escape_message_value(article.get("url", ""))
        source = _escape_message_value(article.get("news_site") or article.get("source") or "Spaceflight News")
        published_at = article.get("published_at")
        summary = article.get("summary") or article.get("description") or article.get("excerpt")

        published_text = ""
        if published_at:
            try:
                published_dt = datetime.fromisoformat(published_at.replace("Z", "+00:00")).astimezone(timezone)
                published_text = published_dt.strftime("%H:%M %Z")
            except ValueError:
                published_text = ""

        lines.append(f"<b>{index}. {title}</b>")
        lines.append(f"Source: {source}")
        if published_text:
            lines.append(f"Published: {published_text}")
        if summary:
            lines.append(_escape_message_value(_truncate_text(summary)))
        if url:
            lines.append(f"<a href=\"{_escape_message_attribute(url)}\">Read full story</a>")
        lines.append("")

    return "\n".join(lines).strip()


def build_no_news_message(timezone_name: str) -> str:
    timezone = pytz.timezone(timezone_name)
    return (
        "<b>Latest Space News</b>\n"
        f"<i>{_escape_message_value(datetime.now(timezone).strftime('%a, %d %b %Y'))}</i>\n\n"
        "No fresh space articles were found in the latest fetch."
    )


def build_start_message(settings: BotSettings | None = None) -> str:
    """Return a welcome message for chats that start or add the bot."""

    runtime_settings = settings or get_settings()
    return (
        "<b>Space News Bot is ready</b>\n"
        "This chat is now registered for the space news digest.\n\n"
        f"Timezone: {_escape_message_value(runtime_settings.timezone_name)}\n"
        f"News limit: {runtime_settings.news_limit}\n"
        "Use /news to request the latest digest now."
    )


def process_telegram_update(update: dict[str, Any], settings: BotSettings | None = None) -> dict[str, Any]:
    """Register Telegram destinations and prepare optional command replies."""

    runtime_settings = settings or get_settings()
    result: dict[str, Any] = {"registered": False, "reply_chat_id": None, "reply_text": None}

    message = update.get("message") or update.get("channel_post")
    if isinstance(message, dict):
        chat = message.get("chat")
        if isinstance(chat, dict) and upsert_registered_chat(chat, runtime_settings):
            result["registered"] = True

        text = message.get("text")
        if isinstance(chat, dict) and isinstance(text, str) and text.startswith("/"):
            command = text.split("@", 1)[0].strip().lower()
            if command in {"/start", "/help", "/news", "/digest"}:
                result["reply_chat_id"] = str(chat.get("id", ""))
                if command == "/start":
                    result["reply_text"] = build_start_message(runtime_settings)
                else:
                    result["reply_text"] = (
                        "<b>Space News Bot</b>\n"
                        "Your chat is registered. The next digest will be sent automatically."
                    )

    membership = update.get("my_chat_member")
    if isinstance(membership, dict):
        chat = membership.get("chat")
        if isinstance(chat, dict) and upsert_registered_chat(chat, runtime_settings):
            result["registered"] = True

    return result


def fetch_telegram_updates(
    token: str,
    offset: int | None = None,
    timeout: int = DEFAULT_LISTENER_TIMEOUT,
    allowed_updates: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Fetch Telegram updates using long polling."""

    endpoint = f"https://api.telegram.org/bot{token}/getUpdates"
    params: dict[str, Any] = {"timeout": timeout}
    if offset is not None:
        params["offset"] = offset
    if allowed_updates:
        params["allowed_updates"] = json.dumps(allowed_updates)

    try:
        response = requests.get(endpoint, params=params, timeout=timeout + 10)
        response.raise_for_status()
        data = response.json()
        if not data.get("ok", False):
            logger.error("Telegram updates request returned an error: %s", data)
            return []

        updates = data.get("result", [])
        if not isinstance(updates, list):
            return []
        return [update for update in updates if isinstance(update, dict)]
    except requests.RequestException as exc:
        logger.error("Telegram updates request failed: %s", exc)
        return []
    except ValueError as exc:
        logger.error("Telegram updates response could not be parsed: %s", exc)
        return []


def send_news_to_channel(articles: list[dict[str, Any]], settings: BotSettings | None = None) -> dict[str, Any]:
    """Send the fetched articles to every registered Telegram destination."""

    runtime_settings = settings or get_settings()
    if not runtime_settings.telegram_bot_token:
        return {
            "ok": False,
            "sent_count": 0,
            "message": "TELEGRAM_BOT_TOKEN is not set.",
        }

    targets = collect_delivery_targets(runtime_settings)
    if not targets:
        return {
            "ok": False,
            "sent_count": 0,
            "message": "No Telegram destinations are registered yet.",
        }

    if not articles:
        message = build_no_news_message(runtime_settings.timezone_name)
        sent_count = 0
        for target in targets:
            if send_telegram_message(runtime_settings.telegram_bot_token, str(target["chat_id"]), message):
                sent_count += 1
        return {
            "ok": sent_count > 0,
            "sent_count": sent_count,
            "message": "No new articles found for today.",
        }

    digest_message = format_article_digest(articles, runtime_settings.timezone_name)
    sent_count = 0
    for target in targets:
        if send_telegram_message(runtime_settings.telegram_bot_token, str(target["chat_id"]), digest_message):
            sent_count += 1

    return {
        "ok": sent_count > 0,
        "sent_count": sent_count,
        "message": f"Sent a digest to {sent_count} destination(s).",
    }


def sync_telegram_targets_once(settings: BotSettings | None = None) -> int:
    """Pull Telegram updates once and register any new destinations."""

    runtime_settings = settings or get_settings()
    if not runtime_settings.telegram_bot_token:
        return 0

    updates = fetch_telegram_updates(
        runtime_settings.telegram_bot_token,
        allowed_updates=["message", "channel_post", "my_chat_member"],
    )

    registered_count = 0
    for update in updates:
        payload = process_telegram_update(update, runtime_settings)
        if payload.get("registered"):
            registered_count += 1

        reply_chat_id = payload.get("reply_chat_id")
        reply_text = payload.get("reply_text")
        if reply_chat_id and reply_text:
            send_telegram_message(runtime_settings.telegram_bot_token, str(reply_chat_id), str(reply_text))

    return registered_count


def post_news() -> dict[str, Any]:
    """Fetch and post the latest news in one step."""

    settings = get_settings()
    if not settings.telegram_bot_token:
        logger.error("TELEGRAM_BOT_TOKEN not found in environment variables.")
        return {
            "ok": False,
            "sent_count": 0,
            "message": "TELEGRAM_BOT_TOKEN is not set.",
        }

    articles = fetch_latest_space_news(limit=settings.news_limit, timezone_name=settings.timezone_name)
    result = send_news_to_channel(articles, settings=settings)
    logger.info(result["message"])
    return result


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
    logger.info("Starting Space News Bot...")
    result = post_news()
    logger.info("Finished: %s", result["message"])
