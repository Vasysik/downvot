from functools import wraps
from config import load_config, AUTO_CREATE_KEY, AUTO_ALLOWED_CHANNEL
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, Message, CallbackQuery
from yt_dlp_host_api.exceptions import APIError
from state import user_data, bot, admin, api
import logging, io, re

logger = logging.getLogger(__name__)

def authorized_users_only(func):
    @wraps(func)
    def wrapper(message):
        if isinstance(message, Message):
            username = str(message.from_user.username)
            chat_id = message.chat.id
        elif isinstance(message, CallbackQuery):
            username = str(message.from_user.username)
            chat_id = message.message.chat.id
        else:
            return
        
        username = str(message.from_user.username)
        CHAT_MEMBER = username in load_config()['ALLOWED_USERS']
        if AUTO_ALLOWED_CHANNEL and not CHAT_MEMBER:
            try:
                member = bot.get_chat_member(chat_id=AUTO_ALLOWED_CHANNEL, user_id=message.from_user.id)
                if member.status in ['member', 'administrator', 'creator']:
                    CHAT_MEMBER = True
                else:
                    CHAT_MEMBER = False
            except Exception as e:
                bot.reply_to(message, f"Произошла ошибка при проверке членства в канале:\n<code>{str(e)}</code>", parse_mode='HTML')
        if CHAT_MEMBER:
            try:
                if chat_id not in user_data: user_data[chat_id] = {}
                user_data[chat_id]['username'] = message.from_user.username
                user_data[chat_id]['client'] = api.get_client(admin.get_key(f'{message.from_user.username}_downvot'))
                return func(message)
            except APIError as e:
                if AUTO_CREATE_KEY:
                    bot.reply_to(message, f"К сожалению, ваш ключ не найден на сервере.\nЯ создам для вас новый ключ.", parse_mode='HTML')
                    try:
                        admin.create_key(f'{message.from_user.username}_downvot', ["get_video", "get_audio", "get_info"])
                        bot.send_message(chat_id, f"Новый ключ создан успешно!", parse_mode='HTML')
                        return func(message)
                    except APIError as e:
                        bot.send_message(chat_id, f"Произошла ошибка при создании ключа:\n<code>{str(e)}</code>", parse_mode='HTML')
                else:
                    bot.reply_to(message, f"Произошла ошибка при инициализации клиента:\n<code>{str(e)}</code>", parse_mode='HTML')
        elif AUTO_ALLOWED_CHANNEL:
            bot.reply_to(message, f"Для использования бота вам необходимо быть подписанным на канал: {AUTO_ALLOWED_CHANNEL}")
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

# Unsafe
# def list_keys(message):
#     try:
#         chat_id = message.chat.id
#         client = user_data[chat_id]['client']
#         keys = client.get_keys()
#         key_list = "Список ключей:\n\n"
#         for user, data in keys.items():
#             key_list += f"Пользователь: <code>{user}</code>\n"
#             key_list += f"Ключ: <tg-spoiler>{data['key']}</tg-spoiler>\n"
#             key_list += f"Права: {data['permissions']}\n\n"
#         return key_list
#     except APIError as e:
#         bot.send_message(chat_id, f"Не получить список ключей.\nОшибка: <code>{str(e)}</code>", parse_mode='HTML')
#     except Exception as e:
#         logger.error(f"Ошибка при обработке запроса для пользователя {chat_id}: {str(e)}")
#         bot.send_message(chat_id, f"Произошла ошибка при обработке запроса:\n<code>{str(e)}</code>", parse_mode='HTML')

def create_key_step(message):
    try:
        chat_id = message.chat.id
        input_text = message.text.strip()
        parts = input_text.split()
        client = user_data[chat_id]['client']

        new_key_username = parts[0]
        permissions = parts[1:] if len(parts) > 1 else ["get_video", "get_audio", "get_info"]

        new_key = client.create_key(f"{new_key_username}", permissions)
        bot.send_message(chat_id, f"Ключ создан успешно.\nПользователь: <code>{new_key_username}</code>\nНовый ключ: <tg-spoiler>{new_key}</tg-spoiler>\nПрава: {permissions}", parse_mode='HTML')
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
        try:
            client.delete_key(f"{user_to_delete}")
            bot.send_message(chat_id, f"Ключ пользователя <code>{user_to_delete}</code> успешно удален.", parse_mode='HTML')
        except APIError as e:
            bot.send_message(chat_id, f"Не удалось удалить ключ на сервере для пользователя <code>{user_to_delete}</code>.\nОшибка: <code>{str(e)}</code>", parse_mode='HTML')
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
    # Unsafe
    # keyboard.row(InlineKeyboardButton("Список ключей", callback_data="admin_list_keys"))
    keyboard.row(InlineKeyboardButton("Создать ключ", callback_data="admin_create_key"))
    keyboard.row(InlineKeyboardButton("Удалить ключ", callback_data="admin_delete_key"))
    return keyboard
