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
            logger.warning(f"Unsupported message type: {type(message)}")
            return
        
        logger.info(f"Authorizing user: {username}")
        CHAT_MEMBER = username in load_config()['ALLOWED_USERS']

        if chat_id not in user_data: 
            user_data[chat_id] = {}
            user_data[chat_id]['language'] = message.from_user.language_code
            logger.info(f"New user data created for {username}")
        
        if AUTO_ALLOWED_CHANNEL and not CHAT_MEMBER:
            try:
                member = bot.get_chat_member(chat_id=AUTO_ALLOWED_CHANNEL, user_id=message.from_user.id)
                if member.status in ['member', 'administrator', 'creator']:
                    CHAT_MEMBER = True
                    logger.info(f"User {username} authorized via channel membership")
                else:
                    CHAT_MEMBER = False
                    logger.info(f"User {username} not a member of the allowed channel")
            except Exception as e:
                logger.error(f"Error checking channel membership for user {username}: {str(e)}")
                bot.reply_to(message, get_string('processing_error', user_data[chat_id]['language']).format(error=str(e)), parse_mode='HTML')
        
        if CHAT_MEMBER:
            try:
                user_data[chat_id]['username'] = message.from_user.username
                user_data[chat_id]['client'] = api.get_client(admin.get_key(f'{message.from_user.username}_downvot'))
                logger.info(f"User {username} successfully authorized")
                return func(message)
            except APIError as e:
                logger.error(f"API Error for user {username}: {str(e)}")
                if AUTO_CREATE_KEY:
                    logger.info(f"Attempting to create key for user {username}")
                    bot.reply_to(message, get_string('key_missing', user_data[chat_id]['language']), parse_mode='HTML')
                    try:
                        admin.create_key(f'{message.from_user.username}_downvot', ["get_video", "get_audio", "get_live_video", "get_live_audio", "get_info"])
                        logger.info(f"Key created successfully for user {username}")
                        bot.send_message(chat_id, get_string('key_created', user_data[chat_id]['language']), parse_mode='HTML')
                        return func(message)
                    except APIError as e:
                        logger.error(f"Error creating key for user {username}: {str(e)}")
                        bot.send_message(chat_id, get_string('key_creation_error', user_data[chat_id]['language']).format(error=str(e)), parse_mode='HTML')
                else:
                    bot.reply_to(message, get_string('processing_error', user_data[chat_id]['language']).format(error=str(e)), parse_mode='HTML')
        elif AUTO_ALLOWED_CHANNEL:
            logger.warning(f"Access denied for user {username}: not a member of the allowed channel")
            bot.reply_to(message, get_string('no_access_chanel', user_data[chat_id]['language']).format(channel=AUTO_ALLOWED_CHANNEL))
        else:
            logger.warning(f"Access denied for user {username}: not in the allowed users list")
            bot.reply_to(message, get_string('no_access', user_data[chat_id]['language']))
    return wrapper

def detect_source(url):
    youtube_patterns = [r'(?:https?:\/\/)?(?:www\.)?(?:youtube\.com|youtu\.be)\/']
    for pattern in youtube_patterns:
        if re.search(pattern, url):
            return 'YouTube'    
    return None
    
def process_request(chat_id, processing_message_id):
    try:
        logger.info(f"Starting request processing for user {chat_id}, message ID: {processing_message_id}")
        processing_data = user_data[chat_id][processing_message_id]
        url = processing_data['url']
        file_type = processing_data['file_type']
        duration = processing_data.get('duration', 30)
        video_format = processing_data['video_format']
        audio_format = processing_data['audio_format']
        username = user_data[chat_id]['username']
        info = processing_data['file_info']
        client = user_data[chat_id]['client']

        logger.info(f"Request details for user {username}: file_type={file_type}, video_format={video_format}, audio_format={audio_format}, duration={duration}")

        video_format_info = info['qualities']["video"][video_format]
        audio_format_info = info['qualities']["audio"][audio_format]
        
        if info['is_live']:
            if file_type == 'video':
                task = client.send_task.get_live_video(url=url, duration=duration, video_format=video_format, audio_format=audio_format)
            else:
                task = client.send_task.get_live_audio(url=url, duration=duration, audio_format=audio_format)
        elif file_type == 'video':
            task = client.send_task.get_video(url=url, video_format=video_format, audio_format=audio_format)
        else:
            task = client.send_task.get_audio(url=url, audio_format=audio_format)

        bot.edit_message_text(get_string('processing_request', user_data[chat_id]['language']), chat_id, processing_message_id)
        
        logger.info(f"Waiting for task result for user {username}")
        task_result = task.get_result()
        file_obj = io.BytesIO(task_result.get_file())

        file_url = task_result.get_file_url()
        file_size = file_obj.getbuffer().nbytes
        max_file_size = 50 * 1024 * 1024  # 50 MB

        if file_size > max_file_size:
            logger.info(f"File size exceeds limit for user {username}. Sending download link.")
            if file_type == 'video': 
                message = get_string('download_complete_video', user_data[chat_id]['language'])
                caption = message.format(url=url, title=info['title'], video_quality=f"{video_format_info['height']}p{video_format_info['fps']}", audio_quality=f"{audio_format_info['abr']}kbps")
                bot.send_photo(chat_id, info['thumbnail'], caption=caption, parse_mode='HTML', reply_markup=file_link_keyboard(user_data[chat_id]['language'], file_url))
            else: 
                message = get_string('download_complete_audio', user_data[chat_id]['language'])
                caption = message.format(url=url, title=info['title'], audio_quality=f"{audio_format_info['abr']}kbps")
                bot.send_message(chat_id, caption, parse_mode='HTML', reply_markup=file_link_keyboard(user_data[chat_id]['language'], file_url))
        else:
            logger.info(f"Preparing to send file for user {username}")
            filename = re.sub(r'[^a-zA-ZÀ-žа-яА-ЯёЁ0-9;_ ]', '', info['title'][:48])
            filename = re.sub(r'\s+', '_', filename) + f'_DownVot'
            if file_type == 'video': 
                filename += f"_{video_format_info['height']}p{video_format_info['fps']}.{file_url.split('.')[-1]}"
            else: 
                filename += f"_{audio_format_info['abr']}kbps.{file_url.split('.')[-1]}"
            file_obj.name = filename

            logger.info(f"Sending file '{filename}' to user {username}")
            if file_type == 'video': 
                message = get_string('download_complete_video', user_data[chat_id]['language'])
                caption = message.format(url=url, title=info['title'], video_quality=f"{video_format_info['height']}p{video_format_info['fps']}", audio_quality=f"{audio_format_info['abr']}kbps")
                bot.send_video(chat_id, file_obj, caption=caption, supports_streaming=True, parse_mode='HTML', reply_markup=file_link_keyboard(user_data[chat_id]['language'], file_url))
            else: 
                message = get_string('download_complete_audio', user_data[chat_id]['language'])
                caption = message.format(url=url, title=info['title'], audio_quality=f"{audio_format_info['abr']}kbps")
                bot.send_audio(chat_id, file_obj, caption=caption, parse_mode='HTML', reply_markup=file_link_keyboard(user_data[chat_id]['language'], file_url))
        logger.info(f"Request processing completed successfully for user {username}")
    except APIError as e:
        logger.error(f"API Error for user {chat_id}: {str(e)}")
        bot.send_message(chat_id, get_string('processing_error', user_data[chat_id]['language']).format(error=str(e)), parse_mode='HTML')
    except Exception as e:
        logger.error(f"Error processing request for user {chat_id}: {str(e)}")
        bot.send_message(chat_id, get_string('processing_error', user_data[chat_id]['language']).format(error=str(e)), parse_mode='HTML')
    finally:
        if processing_message_id in user_data.get(chat_id, {}):
            try:
                bot.delete_message(chat_id, processing_message_id)
            except Exception as e:
                logger.error(f"Failed to delete processing message for user {chat_id}: {str(e)}")
            del user_data[chat_id][processing_message_id]
    bot.send_message(chat_id, get_string('more_requests', user_data[chat_id]['language']))

def create_key_step(message):
    try:
        chat_id = message.chat.id
        input_text = message.text.strip()
        parts = input_text.split()
        client = user_data[chat_id]['client']

        new_key_username = parts[0]
        permissions = parts[1:] if len(parts) > 1 else ["get_video", "get_audio", "get_live_video", "get_live_audio", "get_info"]

        new_key = client.create_key(f"{new_key_username}", permissions)
        bot.send_message(chat_id, get_string('key_created_successfully', user_data[chat_id]['language']).format(username=new_key_username, key=new_key, permissions=permissions), parse_mode='HTML')
    except APIError as e:
        bot.send_message(chat_id, get_string('key_creation_error', user_data[chat_id]['language']).format(error=str(e)), parse_mode='HTML')
    except Exception as e:
        logger.error(f"Error processing request for user {chat_id}: {str(e)}")
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
        logger.error(f"Error processing request for user {chat_id}: {str(e)}")
        bot.send_message(chat_id, get_string('processing_error', user_data[chat_id]['language']).format(error=str(e)), parse_mode='HTML')

def type_keyboard(lang_code):
    keyboard = InlineKeyboardMarkup()
    keyboard.row(InlineKeyboardButton(get_string('video_button', lang_code), callback_data="type_video"),
                 InlineKeyboardButton(get_string('audio_button', lang_code), callback_data="type_audio"))
    return keyboard

def quality_keyboard(qualities, chat_id, processing_message_id, selected_video=None, selected_audio=None):
    keyboard = InlineKeyboardMarkup()
    total_size = 0
    
    video_qualities = list(qualities["video"].items())
    if not selected_video:
        default_video = video_qualities[-1][0]
        user_data[chat_id][processing_message_id]['video_format'] = default_video
    else: 
        default_video = selected_video
    if user_data[chat_id][processing_message_id]['file_type'] == 'video':
        total_size += qualities["video"][default_video]["filesize"]
        video_format = qualities["video"][default_video]
        dynamic_range = 'HDR' if video_format['dynamic_range'] == 'HDR10' else ''
        keyboard.row(InlineKeyboardButton(f"{get_string('video_quality', user_data[chat_id]['language'])} {video_format['height']}p{video_format['fps']} {dynamic_range}", callback_data=f"select_video_quality_{processing_message_id}"))

    audio_qualities = list(qualities["audio"].items())
    if not selected_audio:
        default_audio = audio_qualities[-1][0]
        user_data[chat_id][processing_message_id]['audio_format'] = default_audio
    else: 
        default_audio = selected_audio
    total_size += qualities["audio"][default_audio]["filesize"]
    audio_format = qualities["audio"][default_audio]
    keyboard.row(InlineKeyboardButton(f"{get_string('audio_quality', user_data[chat_id]['language'])} {audio_format['abr']}kbps", callback_data=f"select_audio_quality_{processing_message_id}"))

    keyboard.row(InlineKeyboardButton(f"{get_string('download_button', user_data[chat_id]['language'])} ≈{round(total_size / (1024 * 1024), 1)}MB", callback_data=f"quality_{processing_message_id}_{default_video}_{default_audio}"))
    return keyboard

def video_quality_keyboard(qualities, processing_message_id):
    keyboard = InlineKeyboardMarkup()
    row = []
    unique_qualities = {}
    for quality, data in qualities["video"].items():
        height = data['height']
        fps = data['fps']
        dynamic_range = 'HDR' if data['dynamic_range'] == 'HDR10' else 'SDR'
        key = f'{height}p{fps}{dynamic_range}'
        unique_qualities[key] = (quality, data)
    for key, (quality, data) in unique_qualities.items():
        if len(row) == 2:
            keyboard.row(*row)
            row = []
        size = "≈?MB"
        if data['filesize']: size = f"≈{round(data['filesize'] / (1024 * 1024), 1)}MB"
        dynamic_range = 'HDR' if data['dynamic_range'] == 'HDR10' else ''
        label = f"{data['height']}p{data['fps']} {dynamic_range} {size}"
        row.append(InlineKeyboardButton(label, callback_data=f"video_quality_{quality}_{processing_message_id}"))
    if row:
        keyboard.row(*row)
    keyboard.row(InlineKeyboardButton("<-", callback_data=f"back_to_main_{processing_message_id}"))
    return keyboard

def audio_quality_keyboard(qualities, processing_message_id):
    keyboard = InlineKeyboardMarkup()
    row = []
    unique_qualities = {}
    for quality, data in qualities["audio"].items():
        abr = data['abr']
        key = f'{abr}'
        unique_qualities[key] = (quality, data)
    for key, (quality, data) in unique_qualities.items():
        if len(row) == 2:
            keyboard.row(*row)
            row = []
        size = "≈?MB"
        if data['filesize']: size = f"≈{round(data['filesize'] / (1024 * 1024), 1)}MB"
        label = f"{data['abr']}kbps {size}"
        row.append(InlineKeyboardButton(label, callback_data=f"audio_quality_{quality}_{processing_message_id}"))
    if row:
        keyboard.row(*row)
    keyboard.row(InlineKeyboardButton("<-", callback_data=f"back_to_main_{processing_message_id}"))
    return keyboard

def admin_keyboard(lang_code):
    keyboard = InlineKeyboardMarkup()
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

def file_link_keyboard(lang_code, url):
    keyboard = InlineKeyboardMarkup()
    keyboard.row(InlineKeyboardButton(get_string('file_link', lang_code), url=url))
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
