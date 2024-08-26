import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from functools import wraps
import requests
import json
import logging
import time
import io
import re

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

with open('config.json') as config_file:
    config = json.load(config_file)
    BOT_TOKEN = config['BOT_TOKEN']
    API_BASE_URL = config['API_BASE_URL']
    ALLOWED_USERS = config['ALLOWED_USERS']

bot = telebot.TeleBot(BOT_TOKEN)

user_data = {}

def format_keyboard():
    keyboard = InlineKeyboardMarkup()
    keyboard.row(InlineKeyboardButton("Видео", callback_data="format_video"),
                 InlineKeyboardButton("Аудио", callback_data="format_audio"))
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

def authorized_users_only(func):
    @wraps(func)
    def wrapper(message):
        username = str(message.from_user.username)
        if username in ALLOWED_USERS:
            return func(message)
        else:
            bot.reply_to(message, "Извините, у вас нет доступа к этому боту.")
    return wrapper

@bot.message_handler(commands=['start'])
@authorized_users_only
def start_message(message):
    logger.info(f"Пользователь {message.from_user.username} запустил бота")
    bot.reply_to(message, "Здравствуйте. Я бот для загрузки медиафайлов.\nПожалуйста, отправьте ссылку на YouTube видео.")

@bot.message_handler(commands=['admin'])
@authorized_users_only
def admin_panel(message):
    username = str(message.from_user.username)
    logger.info(f"Пользователь {username} запустил админ панель")
    headers = {"X-API-Key": ALLOWED_USERS[username]}
    
    response = requests.post(f"{API_BASE_URL}/permissions_check", json={"permissions": ["admin"]}, headers=headers)
    
    if response.status_code == 200:
        bot.reply_to(message, "Админ панель:")
    else:
        bot.reply_to(message, "Извините, у вас нет доступа к админ панели.")

@bot.message_handler(func=lambda message: True)
@authorized_users_only
def handle_message(message):
    if message.text.startswith(('http://', 'https://')):
        logger.info(f"Получена ссылка от пользователя {message.from_user.username}: {message.text}")
        user_data[message.chat.id] = {'url': message.text, 'username': message.from_user.username}
        bot.reply_to(message, "Выберите формат для сохранения:", reply_markup=format_keyboard())
    else:
        bot.reply_to(message, "Пожалуйста, отправьте ссылку на YouTube видео.")

@bot.callback_query_handler(func=lambda call: True)
def callback_query(call):
    chat_id = call.message.chat.id
    if call.data.startswith("format_"):
        user_data[chat_id]['format'] = 'video' if call.data.split("_")[1] == 'video' else 'audio'
        bot.edit_message_text("Получение информации о видео.\nПожалуйста, подождите.", chat_id, call.message.message_id)
        try:
            info = get_info(user_data[chat_id]['url'], user_data[chat_id]['username'], '?qualities&title')
            user_data[chat_id]['file_info'] = info
        except Exception as e:
            logger.error(f"Ошибка при получении информации о видео: {str(e)}")
            bot.edit_message_text("Произошла ошибка при получении информации о видео.\nПожалуйста, попробуйте еще раз.", chat_id, call.message.message_id)
        if user_data[chat_id]['format'] == 'video':
            available_qualities = info['qualities']
            user_data[chat_id]['available_qualities'] = available_qualities
            bot.edit_message_text("Выберите качество видео:", chat_id, call.message.message_id, reply_markup=quality_keyboard(available_qualities))  
        else:
            message = bot.edit_message_text("Начинаю обработку запроса.\nПожалуйста, подождите.", chat_id, call.message.message_id)
            user_data[chat_id]['processing_message_id'] = message.message_id
            process_request(chat_id)
    elif call.data.startswith("quality_"):
        user_data[chat_id]['quality'] = call.data.split("_")[1]
        message = bot.edit_message_text("Начинаю обработку запроса.\nПожалуйста, подождите.", chat_id, call.message.message_id)
        user_data[chat_id]['processing_message_id'] = message.message_id
        process_request(chat_id)

def get_info(url, username, args=''):
    headers = {"X-API-Key": ALLOWED_USERS[username]}
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
        file_format = user_data[chat_id]['format']
        quality = user_data[chat_id].get('quality', '360p')
        username = user_data[chat_id]['username']
        info = user_data[chat_id]['file_info']
        
        headers = {"X-API-Key": ALLOWED_USERS[username]}
        data = {
            "url": url,
            "format": file_format,
            "quality": quality
        }
        
        response = requests.post(f"{API_BASE_URL}/download", json=data, headers=headers)
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
                    bot.send_message(chat_id, f"Файл слишком большой для отправки, вот ваша ссылка на файл: {file_url}")
                else:
                    filename = re.sub(r'[^a-zA-Zа-яА-ЯёЁ0-9;_. ]', '', info['title'][:-13])
                    filename = re.sub(r'\s+', '_', filename) + f'_DownVot'

                    if file_format == 'video': filename += f'_{quality}.mp4'
                    else: filename += '.mp3'

                    file_obj = io.BytesIO(file_response.content)
                    file_obj.name = filename

                    if file_format == 'video':
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

def main():
    logger.info("Бот запущен")
    bot.polling(none_stop=True, timeout=120)

if __name__ == "__main__":
    main()
