import os
import importlib.util
import requests
from dotenv import load_dotenv

def main():
    load_dotenv('.env', override=True)
    token = os.getenv('TELEGRAM_BOT_TOKEN')
    print('TOKEN_PRESENT' if token else 'NO_TOKEN', flush=True)

    if token:
        try:
            r = requests.get(f'https://api.telegram.org/bot{token}/getMe', timeout=10)
            print('getMe status', r.status_code, flush=True)
            print('getMe body', r.text, flush=True)
        except Exception as e:
            print('getMe error', e, flush=True)

    # import the bot module and run post_news()
    spec = importlib.util.spec_from_file_location('snb', 'space_news_bot.py')
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    try:
        result = mod.post_news()
        print('post_news result', result, flush=True)
    except Exception as e:
        print('post_news exception', type(e).__name__, e, flush=True)

if __name__ == '__main__':
    main()
