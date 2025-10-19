import logging
import time
from telebot.apihelper import ApiTelegramException
from telebot import types
import telebot.apihelper
from config import load_config, TELEGRAM_API_URL, DEFAULT_LANGUAGE
from handlers import register_handlers
from state import bot
from youtube_search import YoutubeSearch
from utils import get_string
import re, base64

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

if TELEGRAM_API_URL:
    telebot.apihelper.API_URL = TELEGRAM_API_URL
    logger.info(f"Using custom Telegram API URL: {TELEGRAM_API_URL}")
else:
    logger.info("Using default Telegram API URL")

try:
    BOT_USERNAME = bot.get_me().username
    logger.info(f"Bot username: @{BOT_USERNAME}")
except Exception as e:
    logger.error(f"Could not get bot username: {e}. Inline mode with deep links will not work.")
    BOT_USERNAME = None

register_handlers(bot)

@bot.inline_handler(lambda query: len(query.query) > 2 and BOT_USERNAME)
def inline_query(query):
    try:
        search_query = query.query.strip()
        user_lang = query.from_user.language_code or DEFAULT_LANGUAGE
        logger.info(f"Inline search query from {query.from_user.username} (lang: {user_lang}): {search_query}")
        
        results = YoutubeSearch(search_query, max_results=10).to_dict()
        
        inline_results = []
        for i, video in enumerate(results):
            video_id_match = re.search(r'[?&]v=([^&]+)', video['url_suffix'])
            if not video_id_match:
                continue
            
            video_id = video_id_match.group(1)
            video_url = f"https://www.youtube.com/watch?v={video_id}"
            
            encoded_url = base64.urlsafe_b64encode(video_url.encode()).decode().rstrip('=')
            deep_link_url = f"https://t.me/{BOT_USERNAME}?start=dl_{encoded_url}"
            
            keyboard = types.InlineKeyboardMarkup()
            button_text = get_string("inline_download_button", user_lang)
            button = types.InlineKeyboardButton(text=button_text, url=deep_link_url)
            keyboard.add(button)
            
            input_content = types.InputTextMessageContent(
                message_text=f"<a href='{video_url}'>{video['title']}</a>",
                parse_mode='HTML',
                disable_web_page_preview=False
            )
            
            result = types.InlineQueryResultArticle(
                id=str(i),
                title=video['title'],
                description=f"{video.get('channel', '')} • {video.get('duration', 'N/A')}",
                reply_markup=keyboard,
                input_message_content=input_content,
                thumbnail_url=video['thumbnails'][0]
            )
            inline_results.append(result)
            
        bot.answer_inline_query(query.id, inline_results, cache_time=300)

    except Exception as e:
        logger.error(f"Inline query error: {e}", exc_info=True)

def main():
    restart_count = 0
    while True:
        try:
            logger.info(f"Starting bot polling. Restart count: {restart_count}")
            bot.polling(none_stop=True, interval=1, timeout=20)
        except ApiTelegramException as e:
            restart_count += 1
            logger.error(f"Telegram API error: {e}. Restarting bot. Restart count: {restart_count}")
            time.sleep(5)
        except Exception as e:
            restart_count += 1
            logger.error(f"Unexpected error: {e}. Restarting bot. Restart count: {restart_count}")
            time.sleep(5)

if __name__ == "__main__":
    config = load_config()
    logger.info("Bot initialized")
    main()
