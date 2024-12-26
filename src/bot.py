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
            
        # Получаем информацию о видео
        client = utils.get_or_create_client(query.from_user)
        info = client.get_info(url=url).get_json(['qualities', 'title', 'thumbnail', 'is_live', 'duration'])
        
        if info['is_live']:
            return
            
        results = []
        
        # Расчет размера для видео (берем лучшее качество)
        video_format = list(info["qualities"]["video"].items())[-1][1]
        audio_format = list(info["qualities"]["audio"].items())[-1][1]
        video_size = 0
        if video_format['filesize']: 
            video_size = video_format['filesize']
        elif video_format.get('filesize_approx', 0): 
            video_size = video_format['filesize_approx']
        if audio_format['filesize']: 
            video_size += audio_format['filesize']
        elif audio_format.get('filesize_approx', 0): 
            video_size += audio_format.get('filesize_approx', 0)
        
        # Расчет размера для аудио
        audio_size = 0
        if audio_format['filesize']: 
            audio_size = audio_format['filesize']
        elif audio_format.get('filesize_approx', 0): 
            audio_size = audio_format.get('filesize_approx', 0)
        
        # Добавляем видео вариант
        results.append(types.InlineQueryResultArticle(
            id=f"video",
            title=f"Download Video",
            description=f"Size: ≈{round(video_size / (1024 * 1024), 1)}MB",
            thumbnail_url=info['thumbnail'],
            input_message_content=types.InputTextMessageContent(
                message_text="⏳ Downloading..."
            )
        ))
        
        # Добавляем аудио вариант
        results.append(types.InlineQueryResultArticle(
            id=f"audio",
            title=f"Download Audio",
            description=f"Size: ≈{round(audio_size / (1024 * 1024), 1)}MB",
            thumbnail_url=info['thumbnail'],
            input_message_content=types.InputTextMessageContent(
                message_text="⏳ Downloading..."
            )
        ))
            
        bot.answer_inline_query(query.id, results)
        
    except Exception as e:
        logger.error(f"Inline query error: {e}")

# Обработчик выбранного результата
@bot.chosen_inline_handler(func=lambda chosen_inline_result: True)
def chosen_inline_handler(chosen_inline_result):
    try:
        url = chosen_inline_result.query
        result_id = chosen_inline_result.result_id
        inline_message_id = chosen_inline_result.inline_message_id
        
        is_video = result_id == "video"
        
        client = utils.get_or_create_client(chosen_inline_result.from_user)
        info = client.get_info(url=url).get_json(['qualities', 'title'])
        
        # Выбираем лучшее качество
        video_format = list(info["qualities"]["video"].items())[-1][0] if is_video else None
        audio_format = list(info["qualities"]["audio"].items())[-1][0]
        
        # Создаем задачу на скачивание
        if is_video:
            task = client.send_task.get_video(url=url, video_format=video_format, audio_format=audio_format)
        else:
            task = client.send_task.get_audio(url=url, audio_format=audio_format)
            
        # Ждем результат
        task_result = task.get_result(max_retries=config['MAX_GET_RESULT_RETRIES'])
        file_url = task_result.get_file_url()
        
        # Обновляем сообщение с ссылкой или файлом
        bot.edit_inline_message_text(
            text=f"✅ Ready to send!\n{info['title']}\n\n🔗 {file_url}",
            inline_message_id=inline_message_id
        )
        
    except Exception as e:
        logger.error(f"Chosen inline result error: {e}")
        try:
            bot.edit_inline_message_text(
                text=f"❌ Error: {str(e)}",
                inline_message_id=inline_message_id
            )
        except:
            pass

if __name__ == "__main__":
    config = load_config()
    logger.info("Bot initialized")
    main()
