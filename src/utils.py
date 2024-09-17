from functools import wraps
from config import load_config, AUTO_CREATE_KEY, AUTO_ALLOWED_CHANNEL, DEFAULT_LANGUAGE, LANGUAGES
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, Message, CallbackQuery
from yt_dlp_host_api.exceptions import APIError
from state import user_data, bot, admin, api
import logging, io, re, json

logger = logging.getLogger(__name__)

def get_string(key, lang_code=DEFAULT_LANGUAGE):
    if not lang_code in LANGUAGES: lang_code = DEFAULT_LANGUAGE
    if not key in LANGUAGES[lang_code]: lang_code = DEFAULT_LANGUAGE
    if not key in LANGUAGES[lang_code]: return key
    return LANGUAGES[lang_code][key]

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
                bot.reply_to(message, get_string('processing_error', user_data[chat_id]['language']).format(error=str(e)), parse_mode='HTML')
        if CHAT_MEMBER:
            try:
                if chat_id not in user_data: 
                    user_data[chat_id] = {}
                    user_data[chat_id]['language'] = message.from_user.language_code
                user_data[chat_id]['username'] = message.from_user.username
                user_data[chat_id]['client'] = api.get_client(admin.get_key(f'{message.from_user.username}_downvot'))
                return func(message)
            except APIError as e:
                if AUTO_CREATE_KEY:
                    bot.reply_to(message, get_string('key_missing', user_data[chat_id]['language']), parse_mode='HTML')
                    try:
                        admin.create_key(f'{message.from_user.username}_downvot', ["get_video", "get_audio", "get_live_video", "get_live_audio", "get_info"])
                        bot.send_message(chat_id, get_string('key_created', user_data[chat_id]['language']), parse_mode='HTML')
                        return func(message)
                    except APIError as e:
                        bot.send_message(chat_id, get_string('key_creation_error', user_data[chat_id]['language']).format(error=str(e)), parse_mode='HTML')
                else:
                    bot.reply_to(message, get_string('processing_error', user_data[chat_id]['language']).format(error=str(e)), parse_mode='HTML')
        elif AUTO_ALLOWED_CHANNEL:
            bot.reply_to(message, get_string('no_access_chanel', user_data[chat_id]['language']).format(channel=AUTO_ALLOWED_CHANNEL))
        else:
            bot.reply_to(message, get_string('no_access', user_data[chat_id]['language']))
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
        duration = user_data[chat_id].get('duration', 60)
        video_quality = user_data[chat_id].get('video_quality', '360p')
        username = user_data[chat_id]['username']
        info = user_data[chat_id]['file_info']
        client = user_data[chat_id]['client']
        
        if info['is_live']:
            if file_type == 'video':
                task = client.send_task.get_live_video(url=url, duration=duration, video_quality=video_quality)
            else:
                task = client.send_task.get_live_audio(url=url, duration=duration)
        elif file_type == 'video':
            task = client.send_task.get_video(url=url, video_quality=video_quality)
        else:
            task = client.send_task.get_audio(url=url)

        bot.edit_message_text(get_string('processing_request', user_data[chat_id]['language']), chat_id, user_data[chat_id]['processing_message_id'])
        
        task_result = task.get_result()
        file_obj = io.BytesIO(task_result.get_file())

        file_url = task_result.get_file_url()
        file_size = file_obj.getbuffer().nbytes
        max_file_size = 50 * 1024 * 1024  # 50 MB

        if file_size > max_file_size:
            if file_type == 'video': bot.send_photo(chat_id, info['thumbnail'], caption=get_string('download_complete_video_url', user_data[chat_id]['language']).format(file_url=file_url, title=info['title'], video_quality=video_quality), parse_mode='HTML')
            else: bot.send_message(chat_id, get_string('download_complete_audio_url', user_data[chat_id]['language']).format(file_url=file_url, title=info['title']), parse_mode='HTML')
        else:
            filename = re.sub(r'[^a-zA-ZÀ-žа-яА-ЯёЁ0-9;_ ]', '', info['title'][:48])
            filename = re.sub(r'\s+', '_', filename) + f'_DownVot'
            if file_type == 'video': filename += f'_{video_quality}.mp4'
            else: filename += '.mp3'
            file_obj.name = filename

            if file_type == 'video': bot.send_video(chat_id, file_obj, caption=get_string('download_complete_video', user_data[chat_id]['language']).format(file_url=file_url, title=info['title'], video_quality=video_quality), supports_streaming=True, parse_mode='HTML')
            else: bot.send_audio(chat_id, file_obj, caption=get_string('download_complete_audio', user_data[chat_id]['language']).format(file_url=file_url, title=info['title']), parse_mode='HTML')
    except APIError as e:
        bot.send_message(chat_id, get_string('processing_error', user_data[chat_id]['language']).format(error=str(e)), parse_mode='HTML')
    except Exception as e:
        logger.error(f"Ошибка при обработке запроса для пользователя {chat_id}: {str(e)}")
        bot.send_message(chat_id, get_string('processing_error', user_data[chat_id]['language']).format(error=str(e)), parse_mode='HTML')
    finally:
        if 'processing_message_id' in user_data.get(chat_id, {}):
            try:
                bot.delete_message(chat_id, user_data[chat_id]['processing_message_id'])
            except Exception as e:
                logger.error(f"Не удалось удалить сообщение о обработке: {str(e)}")
        language = user_data[chat_id]['language']
        if chat_id in user_data:
            del user_data[chat_id]
            user_data[chat_id] = {}
            user_data[chat_id]['language'] = language
    bot.send_message(chat_id, get_string('more_requests', user_data[chat_id]['language']))

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
        bot.send_message(chat_id, get_string('key_created_successfully', user_data[chat_id]['language']).format(username=new_key_username, key=new_key, permissions=permissions), parse_mode='HTML')
    except APIError as e:
        bot.send_message(chat_id, get_string('key_creation_error', user_data[chat_id]['language']).format(error=str(e)), parse_mode='HTML')
    except Exception as e:
        logger.error(f"Ошибка при обработке запроса для пользователя {chat_id}: {str(e)}")
        bot.send_message(chat_id, get_string('processing_error', user_data[chat_id]['language']).format(error=str(e)), parse_mode='HTML')

def delete_key_step(message):
    try:
        chat_id = message.chat.id
        user_to_delete = message.text.strip()
        client = user_data[chat_id]['client']
        try:
            client.delete_key(f"{user_to_delete}")
            bot.send_message(chat_id, get_string('key_deleted_successfully', user_data[chat_id]['language']).format(username=user_to_delete), parse_mode='HTML')
        except APIError as e:
            bot.send_message(chat_id, get_string('key_deletion_error', user_data[chat_id]['language']).format(error=str(e)), parse_mode='HTML')
    except Exception as e:
        logger.error(f"Ошибка при обработке запроса для пользователя {chat_id}: {str(e)}")
        bot.send_message(chat_id, get_string('processing_error', user_data[chat_id]['language']).format(error=str(e)), parse_mode='HTML')

def type_keyboard(lang_code):
    keyboard = InlineKeyboardMarkup()
    keyboard.row(InlineKeyboardButton(get_string('video_button', lang_code), callback_data="type_video"),
                 InlineKeyboardButton(get_string('audio_button', lang_code), callback_data="type_audio"))
    return keyboard

def quality_keyboard(qualities, chat_id, selected_video=None, selected_audio=None):
    keyboard = InlineKeyboardMarkup()
    row = []

    video_qualities = list(qualities["video"].items())
    if not selected_video:
        default_video = video_qualities[-1][0]
        user_data[chat_id]['video_quality'] = default_video
    else: default_video = selected_video
    row.append(InlineKeyboardButton(f"{default_video}", callback_data="select_video_quality"))

    audio_qualities = list(qualities["audio"].items())
    if not selected_video:
        default_audio = audio_qualities[-1][0]
        user_data[chat_id]['audio_quality'] = default_audio
    else: default_video = selected_video

    row.append(InlineKeyboardButton(f"{default_audio}", callback_data="select_audio_quality"))
    
    total_size = (qualities["video"][default_video]["filesize"] + 
                  qualities["audio"][default_audio]["filesize"]) / (1024 * 1024)
    row.append(InlineKeyboardButton(f"≈{round(total_size, 1)}MB", callback_data=f"quality_{default_video}_{default_audio}"))
    keyboard.row(*row)
    
    return keyboard

def video_quality_keyboard(qualities):
    keyboard = InlineKeyboardMarkup()
    row = []
    for quality, data in qualities["video"].items():
        if len(row) == 2:
            keyboard.row(*row)
            row = []
        label = quality if data['filesize'] == 0 else f"{quality} ≈{round(data['filesize'] / (1024 * 1024), 1)}MB"
        row.append(InlineKeyboardButton(label, callback_data=f"video_quality_{quality}"))
    if row:
        keyboard.row(*row)
    keyboard.row(InlineKeyboardButton("<-", callback_data="back_to_main"))
    return keyboard

def audio_quality_keyboard(qualities):
    keyboard = InlineKeyboardMarkup()
    row = []
    for quality, data in qualities["audio"].items():
        if len(row) == 2:
            keyboard.row(*row)
            row = []
        label = quality if data['filesize'] == 0 else f"{quality} ≈{round(data['filesize'] / (1024 * 1024), 1)}MB"
        row.append(InlineKeyboardButton(label, callback_data=f"audio_quality_{quality}"))
    if row:
        keyboard.row(*row)
    keyboard.row(InlineKeyboardButton("<-", callback_data="back_to_main"))
    return keyboard

def admin_keyboard(lang_code):
    keyboard = InlineKeyboardMarkup()
    # Unsafe
    # keyboard.row(InlineKeyboardButton("Список ключей", callback_data="admin_list_keys"))
    keyboard.row(InlineKeyboardButton(get_string('create_key_button', lang_code), callback_data="admin_create_key"))
    keyboard.row(InlineKeyboardButton(get_string('delete_key_button', lang_code), callback_data="admin_delete_key"))
    return keyboard

def duration_keyboard(lang_code):
    keyboard = InlineKeyboardMarkup()
    row = []
    durations = [30, 60, 120, 180, 240, 300]
    for duration in durations:
        if len(row) == 3:
            keyboard.row(*row)
            row = []
        row.append(InlineKeyboardButton(text=f"{duration} {get_string('second', lang_code)}", callback_data=f"duration_{duration}"))
    if row:
        keyboard.row(*row)
    return keyboard

def language_keyboard():
    keyboard = InlineKeyboardMarkup()
    row = []
    for lang_code in LANGUAGES.keys():
        if len(row) == 3:
            keyboard.row(*row)
            row = []
        row.append(InlineKeyboardButton(get_string('lang_name', lang_code), callback_data=f"lang_{lang_code}"))
    if row:
        keyboard.row(*row)
    return keyboard
