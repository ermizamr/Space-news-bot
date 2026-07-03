---
title: Space News Bot
sdk: gradio
sdk_version: 4.44.1
app_file: app.py
python_version: 3.11
---

# Space News Bot
![Space News Bot](https://i.ibb.co/qLyg9YhC/Gemini-Generated-Image-76vjgk76vjgk76vj-4.png)

A Telegram bot that fetches the latest space news and sends a formatted digest every Ethiopian morning.

## What changed
- The bot logic is now import-safe and uses Telegram's HTTP Bot API directly.
- A Hugging Face Spaces entrypoint is included in [app.py](app.py).
- The UI lets you trigger a send manually, keep a daily scheduler running, and listen for Telegram chats that start the bot or add it.

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
- Each news run is broadcast to every registered destination plus the configured fallback channel.

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
- If you only want the Telegram audience listener disabled, set `ENABLE_TELEGRAM_LISTENER=false`.

## License
This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.
