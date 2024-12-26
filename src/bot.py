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

        results = [
            types.InlineQueryResultArticle(
                id=f"video",
                title=f"Send Video",
                description=f"{best_video[1]['height']}p | {best_audio[1]['abr']}kbps",
                thumbnail_url=info['thumbnail'],
                input_message_content=types.InputTextMessageContent(
                    message_text="Loading video..."
                ),
                reply_markup=types.InlineKeyboardMarkup().add(
                    types.InlineKeyboardButton(
                        text="Send Video",
                        callback_data=f"send_video_{video_task.task_id}"
                    )
                )
            ),
            types.InlineQueryResultArticle(
                id=f"audio",
                title=f"Send Audio",
                description=f"{best_audio[1]['abr']}kbps",
                thumbnail_url=info['thumbnail'],
                input_message_content=types.InputTextMessageContent(
                    message_text="Loading audio..."
                ),
                reply_markup=types.InlineKeyboardMarkup().add(
                    types.InlineKeyboardButton(
                        text="Send Audio", 
                        callback_data=f"send_audio_{audio_task.task_id}"
                    )
                )
            )
        ]
            
        bot.answer_inline_query(query.id, results, cache_time=0)
        
    except Exception as e:
        logger.error(f"Inline query error: {e}")

@bot.callback_query_handler(func=lambda call: call.data.startswith(("send_video_", "send_audio_")))
def callback_download(call):
    try:
        chat_id = call.message.chat.id
        message_id = call.message.message_id
        action, task_id = call.data.split("_", 2)
        
        bot.edit_message_text(
            text="Downloading...",
            chat_id=chat_id,
            message_id=message_id
        )
        
        client = utils.get_or_create_client(call.from_user)
        task_result = client.get_task_result(task_id).get_result(max_retries=5)
        
        file_obj = io.BytesIO(task_result.get_file())
        file_size = file_obj.getbuffer().nbytes
        
        if file_size > 50 * 1024 * 1024:  # 50MB limit
            file_url = task_result.get_file_url()
            keyboard = types.InlineKeyboardMarkup()
            keyboard.add(types.InlineKeyboardButton(text="Download Link", url=file_url))
            bot.edit_message_text(
                text="File is too large to send directly. Use the download link:",
                chat_id=chat_id,
                message_id=message_id,
                reply_markup=keyboard
            )
        else:
            if action == "send_video":
                bot.delete_message(chat_id, message_id)
                bot.send_video(chat_id, file_obj, supports_streaming=True)
            else:
                bot.delete_message(chat_id, message_id)
                bot.send_audio(chat_id, file_obj)
                
    except Exception as e:
        logger.error(f"Download error: {e}")
        bot.edit_message_text(
            text=f"Error occurred: {str(e)}",
            chat_id=chat_id,
            message_id=message_id
        )

if __name__ == "__main__":
    config = load_config()
    logger.info("Bot initialized")
    main()
