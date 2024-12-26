import logging, time
from telebot.apihelper import ApiTelegramException, types
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from config import load_config
from handlers import register_handlers
from state import bot
import utils
import json

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
            
        # Получаем информацию о видео
        client = utils.get_or_create_client(query.from_user)
        info = client.get_info(url=url).get_json(['qualities', 'title', 'thumbnail', 'is_live', 'duration'])
        
        if info['is_live']:
            return

        # Получаем лучшее качество видео и аудио
        best_video = list(info["qualities"]["video"].items())[-1][1]  
        best_audio = list(info["qualities"]["audio"].items())[-1][1]
        
        # Создаем inline результаты
        results = []
        
        # Опция видео
        video_size = best_video.get('filesize', 0) + best_audio.get('filesize', 0)
        if not video_size:
            video_size = best_video.get('filesize_approx', 0) + best_audio.get('filesize_approx', 0)
        video_size_mb = round(video_size / (1024 * 1024), 1)
        
        results.append(types.InlineQueryResultArticle(
            id=f"video",
            title=f"Download Video",
            description=f"{best_video['height']}p | {best_audio['abr']}kbps | ≈{video_size_mb}MB",
            thumbnail_url=info['thumbnail'],
            input_message_content=types.InputTextMessageContent(
                message_text=json.dumps({
                    'url': url,
                    'type': 'video',
                    'video_format': list(info["qualities"]["video"].items())[-1][0],
                    'audio_format': list(info["qualities"]["audio"].items())[-1][0],
                    'title': info['title']
                })
            )
        ))
        
        # Опция аудио
        audio_size = best_audio.get('filesize', 0) or best_audio.get('filesize_approx', 0)
        audio_size_mb = round(audio_size / (1024 * 1024), 1)
        
        results.append(types.InlineQueryResultArticle(
            id=f"audio",
            title=f"Download Audio",
            description=f"{best_audio['abr']}kbps | ≈{audio_size_mb}MB",
            thumbnail_url=info['thumbnail'],
            input_message_content=types.InputTextMessageContent(
                message_text=json.dumps({
                    'url': url,
                    'type': 'audio',
                    'audio_format': list(info["qualities"]["audio"].items())[-1][0],
                    'title': info['title']
                })
            )
        ))
            
        bot.answer_inline_query(query.id, results)
        
    except Exception as e:
        logger.error(f"Inline query error: {e}")

@bot.message_handler(func=lambda message: True)
def handle_json_message(message):
    try:
        data = json.loads(message.text)
        if not isinstance(data, dict):
            return
            
        chat_id = message.chat.id
        processing_message = bot.edit_message_text(
            text=f"Downloading {data['title']}...",
            chat_id=chat_id,
            message_id=message.message_id
        )
        
        client = utils.get_or_create_client(message.from_user)
        
        if data['type'] == 'video':
            task = client.send_task.get_video(
                url=data['url'],
                video_format=data['video_format'],
                audio_format=data['audio_format']
            )
        else:
            task = client.send_task.get_audio(
                url=data['url'],
                audio_format=data['audio_format']
            )
            
        task_result = task.get_result(max_retries=MAX_GET_RESULT_RETRIES)
        file_url = task_result.get_file_url()
        
        file_obj = io.BytesIO(task_result.get_file())
        file_size = file_obj.getbuffer().nbytes
        max_file_size = 50 * 1024 * 1024  # 50 MB
        
        if file_size > max_file_size:
            keyboard = InlineKeyboardMarkup()
            keyboard.add(InlineKeyboardButton(text="Download Link", url=file_url))
            bot.edit_message_text(
                text=f"File is too large to send directly. Use the download link:",
                chat_id=chat_id,
                message_id=processing_message.message_id,
                reply_markup=keyboard
            )
        else:
            if data['type'] == 'video':
                bot.delete_message(chat_id, processing_message.message_id)
                bot.send_video(
                    chat_id,
                    file_obj,
                    caption=f"{data['title']}",
                    supports_streaming=True
                )
            else:
                bot.delete_message(chat_id, processing_message.message_id)
                bot.send_audio(
                    chat_id,
                    file_obj,
                    caption=f"{data['title']}"
                )
                
    except Exception as e:
        logger.error(f"Error processing message: {e}")
        try:
            bot.edit_message_text(
                text=f"Error occurred while processing: {str(e)}",
                chat_id=chat_id,
                message_id=processing_message.message_id
            )
        except:
            pass

if __name__ == "__main__":
    config = load_config()
    logger.info("Bot initialized")
    main()
