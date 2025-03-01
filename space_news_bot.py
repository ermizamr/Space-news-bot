# this code was written precisely to be run on PythonAnyWhere free version and to an Ethiopian telegram channel to post selected space news on morning.
# so the code here is optimized while working not to pass 100 seconds per day and to align with Ethiopia's morning time.
# you can edit whatever you want.

import os
import requests
from telegram import Bot
from datetime import datetime
import pytz
import logging

# --- Configuration ---
BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
if not BOT_TOKEN:
    logging.error("Error: TELEGRAM_BOT_TOKEN environment variable not set. Exiting.")
    exit(1)

CHANNEL_ID = '@channel_of_ermi'  # Use your channel username or ID
ETHIOPIA_TZ = pytz.timezone('Africa/Addis_Ababa')

# --- Functions ---
def fetch_latest_space_news():
    """Fetches the latest space news articles from the API."""
    url = "https://api.spaceflightnewsapi.net/v4/articles/?limit=5"  # Fetch only 5 articles
    try:
        response = requests.get(url)
        response.raise_for_status()  # Raise HTTPError for bad responses
        data = response.json()

        # Get today's date in Ethiopian time
        today = datetime.now(ETHIOPIA_TZ).date()

        # Filter articles published today
        today_articles = [
            article
            for article in data["results"]
            if datetime.fromisoformat(article["published_at"].replace("Z", "+00:00")).astimezone(ETHIOPIA_TZ).date() == today
        ]

        return today_articles

    except requests.exceptions.RequestException as e:
        logging.error(f"API Error: {e}")
        return []
    except Exception as e:
        logging.error(f"Unexpected Error: {e}")
        return []

def send_news_to_channel(articles):
    """Sends news articles to the Telegram channel. Skips images to save time."""
    bot = Bot(token=BOT_TOKEN)

    if not articles:
        message = "No space news articles available for today."
        try:
            bot.send_message(chat_id=CHANNEL_ID, text=message)
        except Exception as e:
            logging.error(f"Telegram Error: {e}")
        return

    for article in articles:
        title = article['title']
        url = article['url']
        message = f"{title}\n{url}"

        try:
            # Skip image handling to save time
            bot.send_message(chat_id=CHANNEL_ID, text=message)
        except Exception as e:
            logging.error(f"Telegram Error: {e}")

def post_news():
    """Fetches and sends the news to the channel."""
    articles = fetch_latest_space_news()
    send_news_to_channel(articles)

# --- Main ---
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

    # Fetch and send the latest news to the channel
    post_news()

    logging.info("Script execution completed.")
