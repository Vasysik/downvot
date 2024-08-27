from functools import wraps
from config import save_config, load_config
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from yt_dlp_host_api.exceptions import APIError
from state import user_data, bot
import logging, io, re

logger = logging.getLogger(__name__)

def authorized_users_only(func):
    @wraps(func)
    def wrapper(message):
        username = str(message.from_user.username)
        if username in load_config()['ALLOWED_USERS']:
            return func(message)
        else:
            bot.reply_to(message, "Извините, у вас нет доступа к этому боту.")
    return wrapper

def detect_source(url):
    youtube_patterns = [r'(?:https?:\/\/)?(?:www\.)?(?:youtube\.com|youtu\.be)\/']
    for pattern in youtube_patterns:
        if re.search(pattern, url):
            return 'YouTube'    
    return None
    
def process_request(chat_id):
    try:
        url = user_data[chat_id]['url']
        file_type = user_data[chat_id]['file_type']
        quality = user_data[chat_id].get('quality', '360p')
        username = user_data[chat_id]['username']
        info = user_data[chat_id]['file_info']
        client = user_data[chat_id]['client']
        
        if file_type == 'video':
            task = client.send_task.get_video(url=url, quality=quality)
        else:
            task = client.send_task.get_audio(url=url)

        bot.edit_message_text(f"Задача на загрузку создана.\nОжидаем завершения...", chat_id, user_data[chat_id]['processing_message_id'])
        
        task_result = task.get_result()
        file_obj = io.BytesIO(task_result.get_file())

        file_size = file_obj.getbuffer().nbytes
        max_file_size = 50 * 1024 * 1024  # 50 MB

        if file_size > max_file_size:
            file_url = task_result.get_file_url()
            bot.send_message(chat_id, f"Файл слишком большой для отправки, вот ваша ссылка на файл:\n{file_url}")
        else:
            filename = re.sub(r'[^a-zA-ZÀ-žа-яА-ЯёЁ0-9;_ ]', '', info['title'])
            filename = re.sub(r'\s+', '_', filename) + f'_DownVot'
            if file_type == 'video': filename += f'_{quality}.mp4'
            else: filename += '.mp3'
            file_obj.name = filename

            if file_type == 'video': bot.send_video(chat_id, file_obj, caption="Ваше видео готово!", supports_streaming=True)
            else: bot.send_audio(chat_id, file_obj, caption="Ваше аудио готово!")
    except APIError as e:
        bot.send_message(chat_id, f"Произошла ошибка при обработке запроса:\n<code>{str(e)}</code>", parse_mode='HTML')
    except Exception as e:
        logger.error(f"Ошибка при обработке запроса для пользователя {chat_id}: {str(e)}")
        bot.send_message(chat_id, f"Произошла ошибка при обработке запроса:\n<code>{str(e)}</code>", parse_mode='HTML')
    finally:
        if 'processing_message_id' in user_data.get(chat_id, {}):
            try:
                bot.delete_message(chat_id, user_data[chat_id]['processing_message_id'])
            except Exception as e:
                logger.error(f"Не удалось удалить сообщение о обработке: {str(e)}")
        
        if chat_id in user_data:
            del user_data[chat_id]
    
    bot.send_message(chat_id, "Если у вас есть еще запросы, пожалуйста, отправьте новую ссылку.")

def create_key_step(message):
    try:
        chat_id = message.chat.id
        new_key_username = message.text.strip()
        client = user_data[chat_id]['client']
        new_key = client.admin.create_key(f"{new_key_username}-downbot", ["get_video", "get_audio", "get_info"])['key']
        bot.send_message(chat_id, f"Ключ создан успешно.\nПользователь: <code>{new_key_username}</code>\nНовый ключ: <tg-spoiler>{new_key}</tg-spoiler>", parse_mode='HTML')

        config = load_config()
        config['ALLOWED_USERS'][new_key_username] = new_key
        save_config(config)
    except APIError as e:
        bot.send_message(chat_id, f"Не удалось создать ключ.\nОшибка: <code>{str(e)}</code>", parse_mode='HTML')
    except Exception as e:
        logger.error(f"Ошибка при обработке запроса для пользователя {chat_id}: {str(e)}")
        bot.send_message(chat_id, f"Произошла ошибка при обработке запроса:\n<code>{str(e)}</code>", parse_mode='HTML')

def delete_key_step(message):
    try:
        chat_id = message.chat.id
        user_to_delete = message.text.strip()
        client = user_data[chat_id]['client']

        config = load_config()
        if user_to_delete in config['ALLOWED_USERS']:
            try:
                client.admin.delete_key(f"{user_to_delete}-downbot")
                del config['ALLOWED_USERS'][user_to_delete]
                save_config(config)
                
                bot.send_message(chat_id, f"Ключ пользователя <code>{user_to_delete}</code> успешно удален.", parse_mode='HTML')
            except APIError as e:
                bot.send_message(chat_id, f"Не удалось удалить ключ на сервере для пользователя <code>{user_to_delete}</code>.\nОшибка: <code>{str(e)}</code>", parse_mode='HTML')
        else:
            bot.send_message(chat_id, f"Пользователь <code>{user_to_delete}</code> не найден в списке разрешенных пользователей.", parse_mode='HTML')
    except Exception as e:
        logger.error(f"Ошибка при обработке запроса для пользователя {chat_id}: {str(e)}")
        bot.send_message(chat_id, f"Произошла ошибка при обработке запроса:\n<code>{str(e)}</code>", parse_mode='HTML')

def type_keyboard():
    keyboard = InlineKeyboardMarkup()
    keyboard.row(InlineKeyboardButton("Видео", callback_data="type_video"),
                 InlineKeyboardButton("Аудио", callback_data="type_audio"))
    return keyboard

def quality_keyboard(available_qualities):
    keyboard = InlineKeyboardMarkup()
    row = []
    for quality in available_qualities:
        if len(row) == 2:
            keyboard.row(*row)
            row = []
        row.append(InlineKeyboardButton(quality, callback_data=f"quality_{quality}"))
    if row:
        keyboard.row(*row)
    return keyboard

def admin_keyboard():
    keyboard = InlineKeyboardMarkup()
    keyboard.row(InlineKeyboardButton("Список ключей", callback_data="admin_list_keys"))
    keyboard.row(InlineKeyboardButton("Создать ключ", callback_data="admin_create_key"))
    keyboard.row(InlineKeyboardButton("Удалить ключ", callback_data="admin_delete_key"))
    return keyboard
