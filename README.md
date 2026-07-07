---
title: Space News Bot
emoji: 🚀
colorFrom: indigo
colorTo: blue
sdk: gradio
sdk_version: 4.44.1
app_file: app.py
python_version: "3.11"
pinned: false
license: mit
short_description: Daily Telegram digest of the latest space news.
tags:
  - telegram
  - news
  - bot
  - space
---

# Space News Bot
![Space News Bot](https://i.ibb.co/qLyg9YhC/Gemini-Generated-Image-76vjgk76vjgk76vj-4.png)

A Telegram bot that fetches the latest space news and sends a formatted digest every Ethiopian morning.

## Features
- Fetches the latest articles from the [Spaceflight News API](https://api.spaceflightnewsapi.net/) and formats a compact HTML digest.
- Runs as a Hugging Face Gradio Space via [app.py](app.py), with a small control panel to send on demand and inspect configuration.
- Keeps a background daily scheduler that posts at a configurable time in your timezone.
- Listens for Telegram `/start`, group adds, and channel adds to auto-register delivery destinations.
- Import-safe core in [space_news_bot.py](space_news_bot.py) that also runs as a one-shot CLI post.

## Deploy on Hugging Face Spaces
1. Create a new Space and choose the Gradio SDK.
2. Upload this repository as-is.
3. Add the following Space secrets or variables:
   - `TELEGRAM_BOT_TOKEN`
   - `CHANNEL_ID`
   - Optional: `ENABLE_TELEGRAM_LISTENER=true`
   - Optional: `TELEGRAM_TARGETS_FILE=telegram_targets.json`
   - Optional: `ENABLE_SCHEDULER=true`
   - Optional: `DAILY_POST_TIME=06:00`
   - Optional: `NEWS_LIMIT=5`
   - Optional: `BOT_TIMEZONE=Africa/Addis_Ababa`
4. The Space will start from [app.py](app.py) and expose a small control panel.

## Telegram audience behavior
- Private chats are registered when someone sends `/start` to the bot.
- Groups are registered when the bot is added or when a member uses the bot in the group.
- Channels are registered when the bot is added as an admin and Telegram delivers channel post updates.
- Each news run is broadcast to **every** registered destination plus the configured fallback channel.
- Chats that block, remove, or deactivate the bot are detected on send and automatically pruned from the registry.

## Commands
- `/news` or `/digest` — reply with the latest space news digest immediately.
- `/start` — subscribe the chat and show the daily schedule.
- `/help` — list the available commands.

## Local run
1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
2. Configure environment variables in `.env` using [.env.example](.env.example) as a guide.
3. Start the Hugging Face app locally:
   ```bash
   python app.py
   ```
4. To run a one-shot post instead:
   ```bash
   python space_news_bot.py
   ```

## Notes
- The Space uses the Spaceflight News API and sends the latest articles in the configured Ethiopian morning schedule.
- If you only want manual sends, set `ENABLE_SCHEDULER=false`.
- To disable the Telegram audience listener, set `ENABLE_TELEGRAM_LISTENER=false`.
- **Persistence:** registered destinations are stored in `TELEGRAM_TARGETS_FILE` (default `telegram_targets.json`).
  On a free Space this filesystem is ephemeral, so registrations reset when the Space restarts. To keep them,
  attach [persistent storage](https://huggingface.co/docs/hub/spaces-storage) and point `TELEGRAM_TARGETS_FILE` at `/data/telegram_targets.json`.
- The listener uses Telegram long polling (`getUpdates`), so make sure no webhook is set on the bot token.

## License
This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.
