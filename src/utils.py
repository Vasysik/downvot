from functools import wraps
from config import save_config, load_config, API_BASE_URL
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from state import user_data, bot
import logging, io, requests, re, time

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

def get_info(url, username, args=''):
    headers = {"X-API-Key": load_config()['ALLOWED_USERS'][username]}
    try:
        response = requests.post(f"{API_BASE_URL}/get_info", json={"url": url}, headers=headers)
        response.raise_for_status()
        task_id = response.json()['task_id']
        
        while True:
            status_response = requests.get(f"{API_BASE_URL}/status/{task_id}", headers=headers)
            status_response.raise_for_status()
            status_data = status_response.json()
            
            if status_data['status'] == 'completed':
                file_path = status_data['file']
                info_response = requests.get(f"{API_BASE_URL}{file_path}{args}", headers=headers)
                info_response.raise_for_status()
                return info_response.json()
            elif status_data['status'] == 'error':
                raise Exception(f"Задача завершилась с ошибкой: {status_data['error']}")
            time.sleep(2)
    except requests.exceptions.RequestException as e:
        logger.error(f"Ошибка при запросе к API: {str(e)}")
        raise Exception(f"Ошибка при взаимодействии с API: {str(e)}")
    
def process_request(chat_id):
    try:
        url = user_data[chat_id]['url']
        file_type = user_data[chat_id]['file_type']
        quality = user_data[chat_id].get('quality', '360p')
        username = user_data[chat_id]['username']
        info = user_data[chat_id]['file_info']
        
        headers = {"X-API-Key": load_config()['ALLOWED_USERS'][username]}
        data = {
            "url": url,
            "file_type": file_type,
            "quality": quality
        }
        
        response = requests.post(f"{API_BASE_URL}/get_video", json=data, headers=headers)
        response.raise_for_status()
        task_id = response.json()['task_id']
        bot.edit_message_text(f"Задача на загрузку создана.\nОжидаем завершения...", chat_id, user_data[chat_id]['processing_message_id'])
        
        while True:
            status_response = requests.get(f"{API_BASE_URL}/status/{task_id}", headers=headers)
            status_response.raise_for_status()
            status_data = status_response.json()
            
            if status_data['status'] == 'completed':
                file_path = status_data['file']
                file_url = f"{API_BASE_URL}{file_path}"

                file_response = requests.get(file_url, headers=headers, stream=True)
                file_response.raise_for_status()

                file_size = int(file_response.headers.get('content-length', -1))
                max_file_size = 50 * 1024 * 1024  # 50 MB

                if file_size > max_file_size:
                    bot.send_message(chat_id, f"Файл слишком большой для отправки, вот ваша ссылка на файл:\n{file_url}")

                    break
                else:
                    filename = re.sub(r'[^a-zA-ZÀ-žа-яА-ЯёЁ0-9;_ ]', '', info['title'])
                    filename = re.sub(r'\s+', '_', filename) + f'_DownVot'
                    if file_type == 'video': filename += f'_{quality}.mp4'
                    else: filename += '.mp3'

                    file_obj = io.BytesIO(file_response.content)
                    file_obj.name = filename

                    if file_type == 'video':
                        bot.send_video(chat_id, file_obj, caption="Ваше видео готово!", supports_streaming=True)
                    else:
                        bot.send_audio(chat_id, file_obj, caption="Ваше аудио готово!")
                    
                    break
            elif status_data['status'] == 'error':
                raise Exception(f"Задача завершилась с ошибкой: {status_data['error']}")
            
            time.sleep(2)
    except Exception as e:
        logger.error(f"Ошибка при обработке запроса для пользователя {chat_id}: {str(e)}")
        bot.send_message(chat_id, f"Произошла ошибка при обработке запроса: {str(e)}")
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
    chat_id = message.chat.id
    username = str(message.from_user.username)
    new_key_username = message.text.strip()
    
    headers = {"X-API-Key": load_config()['ALLOWED_USERS'][username]}
    data = {
        'name': f"{new_key_username}-downbot",
        'permissions': ["get_video", "get_info"]
    }
    
    response = requests.post(f"{API_BASE_URL}/create_key", json=data, headers=headers)
    
    if response.status_code == 201:
        new_key = response.json()['key']
        bot.send_message(chat_id, f"Ключ создан успешно.\nПользователь: {new_key_username}\nНовый ключ: <tg-spoiler>{new_key}</tg-spoiler>", parse_mode='HTML')

        config = load_config()
        config['ALLOWED_USERS'][new_key_username] = new_key
        save_config(config)
    else:
        bot.send_message(chat_id, "Не удалось создать ключ.")

def delete_key_step(message):
    chat_id = message.chat.id
    username = str(message.from_user.username)
    user_to_delete = message.text.strip()
    
    config = load_config()
    if user_to_delete in config['ALLOWED_USERS']:
        key_to_delete = config['ALLOWED_USERS'][user_to_delete]
        headers = {"X-API-Key": config['ALLOWED_USERS'][username]}
        
        response = requests.delete(f"{API_BASE_URL}/delete_key/{user_to_delete}-downbot", headers=headers)
        
        if response.status_code == 200:
            del config['ALLOWED_USERS'][user_to_delete]
            save_config(config)
            bot.send_message(chat_id, f"Ключ пользователя {user_to_delete} успешно удален.")
        else:
            bot.send_message(chat_id, f"Не удалось удалить ключ на сервере для пользователя {user_to_delete}.")
    else:
        bot.send_message(chat_id, f"Пользователь {user_to_delete} не найден в списке разрешенных пользователей.")

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
