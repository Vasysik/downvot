import logging, time
from telebot.apihelper import ApiTelegramException, types
from config import load_config
from handlers import register_handlers
from state import bot
import utils

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

register_handlers(bot)

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

@bot.inline_handler(lambda query: len(query.query) > 0)
def inline_query(query):
    try:
        url = query.query.strip()
        if not url.startswith(('http://', 'https://')):
            return
            
        source = utils.detect_source(url)
        if not source:
            return
        
        client = utils.get_or_create_client(query.from_user)
        info = client.get_info(url=url).get_json(['qualities', 'title', 'thumbnail', 'is_live', 'duration'])
        
        if info['is_live']:
            return
        
        results = []
        
        for quality, data in info["qualities"]["video"].items():
            video_format = data
            audio_format = list(info["qualities"]["audio"].items())[-1][1]
            
            results.append(types.InlineQueryResultArticle(
                id=f"video_{quality}",
                title=f"Video {video_format['height']}p{video_format['fps']}",
                description=f"Audio: {audio_format['abr']}kbps",
                thumb_url=info['thumbnail'],
                input_message_content=types.InputTextMessageContent(
                    message_text=f"Processing video: {info['title']}"
                )
            ))
         
        for quality, data in info["qualities"]["audio"].items():
            results.append(types.InlineQueryResultArticle(
                id=f"audio_{quality}",
                title=f"Audio {data['abr']}kbps",
                description="Audio only",
                thumb_url=info['thumbnail'],
                input_message_content=types.InputTextMessageContent(
                    message_text=f"Processing audio: {info['title']}"
                )
            ))
            
        bot.answer_inline_query(query.id, results)
    except Exception as e:
        logger.error(f"Inline query error: {e}")

if __name__ == "__main__":
    config = load_config()
    logger.info("Bot initialized")
    main()
