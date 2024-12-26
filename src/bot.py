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
            results = [
                types.InlineQueryResultArticle(
                    id="1",
                    title="Live Stream",
                    description="Live streams are not supported",
                    input_message_content=types.InputTextMessageContent(
                        message_text="❌ Live streams are not supported"
                    )
                )
            ]
            return bot.answer_inline_query(query.id, results, cache_time=0)
        
        best_video = list(info["qualities"]["video"].items())[-1]
        best_audio = list(info["qualities"]["audio"].items())[-1]
        
        # Добавим отладочную информацию
        print(f"Processing URL: {url}")
        print(f"Title: {info['title']}")
        print(f"Video quality: {best_video[1]['height']}p")
        print(f"Audio quality: {best_audio[1]['abr']}kbps")
        
        video_task = client.send_task.get_video(
            url=url,
            video_format=best_video[0],
            audio_format=best_audio[0]
        )

        audio_task = client.send_task.get_audio(
            url=url,
            audio_format=best_audio[0]
        )

        print("Waiting for video download...")
        video_result = video_task.get_result(max_retries=config['MAX_GET_RESULT_RETRIES'])
        print("Waiting for audio download...")
        audio_result = audio_task.get_result(max_retries=config['MAX_GET_RESULT_RETRIES'])

        video_url = video_result.get_file_url()
        audio_url = audio_result.get_file_url()

        print(f"Video URL: {video_url}")
        print(f"Audio URL: {audio_url}")

        results = [
            types.InlineQueryResultVideo(
                id="1",
                video_url=video_url,
                mime_type="video/mp4",
                thumbnail_url=info['thumbnail'],
                title=f"{info['title']} - {best_video[1]['height']}p",
                description=f"Video Quality: {best_video[1]['height']}p\nAudio Quality: {best_audio[1]['abr']}kbps\nDuration: {info['duration']} seconds",
                video_width=best_video[1]['width'],
                video_height=best_video[1]['height']
            ),
            types.InlineQueryResultAudio(
                id="2",
                audio_url=audio_url,
                title=info['title'],
                performer=f"Audio {best_audio[1]['abr']}kbps",
                audio_duration=info['duration']
            )
        ]
            
        bot.answer_inline_query(query.id, results, cache_time=0)
        
    except Exception as e:
        logger.error(f"Inline query error: {e}")
        import traceback
        logger.error(traceback.format_exc())
        
        results = [
            types.InlineQueryResultArticle(
                id="1",
                title="Error",
                description=str(e),
                input_message_content=types.InputTextMessageContent(
                    message_text=f"❌ Error occurred: {str(e)}"
                )
            )
        ]
        bot.answer_inline_query(query.id, results, cache_time=0)

if __name__ == "__main__":
    config = load_config()
    logger.info("Bot initialized")
    main()
