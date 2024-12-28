import logging, time
from telebot.apihelper import ApiTelegramException, types
from config import load_config
from handlers import register_handlers
from state import bot
import utils
import io

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
        
        best_video = list(info["qualities"]["video"].items())[-1]
        best_audio = list(info["qualities"]["audio"].items())[-1]
        
        video_task = client.send_task.get_video(
            url=url,
            video_format=best_video[0],
            audio_format=best_audio[0]
        )

        audio_task = client.send_task.get_audio(
            url=url,
            audio_format=best_audio[0]
        )

        logger.info(f'inline tasks: {video_task.task_id} {audio_task.task_id}')

        video_result = video_task.get_result(max_retries=config['MAX_GET_RESULT_RETRIES'])
        audio_result = audio_task.get_result(max_retries=config['MAX_GET_RESULT_RETRIES'])

        results = [
            types.InlineQueryResultVideo(
                id="video",
                video_url=f'{video_result.get_file_url()}?raw=true',
                title=f"Video: {info['title']}",
                thumbnail_url=info['thumbnail'],
                mime_type="video/mp4"
            ),
            types.InlineQueryResultAudio(
                id="audio",
                audio_url=f'{audio_result.get_file_url()}?raw=true',
                title=f"Audio: {info['title']}"
            )
        ]
            
        bot.answer_inline_query(query.id, results, cache_time=0)
        
    except Exception as e:
        logger.error(f"Inline query error: {e}")

if __name__ == "__main__":
    config = load_config()
    logger.info("Bot initialized")
    main()
