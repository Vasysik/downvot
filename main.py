import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import requests
import json
import os
import logging
import time

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Загрузка конфигурации
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

@bot.message_handler(commands=['start'])
def start_message(message):
    username = str(message.from_user.username)
    if username in ALLOWED_USERS:
        logger.info(f"Пользователь {username} запустил бота")
        bot.reply_to(message, "Здравствуйте. Я бот для загрузки медиафайлов. Пожалуйста, отправьте ссылку на YouTube видео.")
    else:
        bot.reply_to(message, "Извините, у вас нет доступа к этому боту.")

@bot.message_handler(func=lambda message: True)
def handle_message(message):
    username = str(message.from_user.username)
    if username in ALLOWED_USERS:
        if message.text.startswith(('http://', 'https://')):
            logger.info(f"Получена ссылка от пользователя {username}: {message.text}")
            user_data[message.chat.id] = {'url': message.text, 'username': username}
            bot.reply_to(message, "Выберите формат для сохранения:", reply_markup=format_keyboard())
        else:
            bot.reply_to(message, "Пожалуйста, отправьте ссылку на YouTube видео.")
    else:
        bot.reply_to(message, "Извините, у вас нет доступа к этому боту.")

@bot.callback_query_handler(func=lambda call: True)
def callback_query(call):
    chat_id = call.message.chat.id
    if call.data.startswith("format_"):
        user_data[chat_id]['format'] = 'video' if call.data.split("_")[1] == 'video' else 'audio'
        if user_data[chat_id]['format'] == 'video':
            bot.edit_message_text("Получение доступного качества. Пожалуйста, подождите.", chat_id, call.message.message_id)
            try:
                available_qualities = get_available_qualities(user_data[chat_id]['url'], user_data[chat_id]['username'])
                user_data[chat_id]['available_qualities'] = available_qualities
                bot.edit_message_text("Выберите качество видео:", chat_id, call.message.message_id, reply_markup=quality_keyboard(available_qualities))
            except Exception as e:
                logger.error(f"Ошибка при получении доступных качеств: {str(e)}")
                bot.edit_message_text("Произошла ошибка при получении доступных качеств. Пожалуйста, попробуйте еще раз.", chat_id, call.message.message_id)
        else:
            message = bot.edit_message_text("Начинаю обработку запроса. Пожалуйста, подождите.", chat_id, call.message.message_id)
            user_data[chat_id]['processing_message_id'] = message.message_id
            process_request(chat_id)
    elif call.data.startswith("quality_"):
        user_data[chat_id]['quality'] = call.data.split("_")[1]
        message = bot.edit_message_text("Начинаю обработку запроса. Пожалуйста, подождите.", chat_id, call.message.message_id)
        user_data[chat_id]['processing_message_id'] = message.message_id
        process_request(chat_id)

def get_available_qualities(url, username):
    headers = {"X-API-Key": ALLOWED_USERS[username]}
    try:
        response = requests.post(f"{API_BASE_URL}/get_info", json={"url": url}, headers=headers)
        response.raise_for_status()  # Это вызовет исключение для неуспешных статус-кодов
        task_id = response.json()['task_id']
        
        while True:
            status_response = requests.get(f"{API_BASE_URL}/status/{task_id}", headers=headers)
            status_response.raise_for_status()
            status_data = status_response.json()
            
            if status_data['status'] == 'completed':
                file_path = status_data['file']
                info_response = requests.get(f"{API_BASE_URL}{file_path}?qualities", headers=headers)
                info_response.raise_for_status()
                qualities = info_response.json()['qualities']
                return qualities
            elif status_data['status'] == 'failed':
                raise Exception(f"Задача завершилась с ошибкой: {status_data.get('error', 'Неизвестная ошибка')}")
            time.sleep(2)
    except requests.exceptions.RequestException as e:
        logger.error(f"Ошибка при запросе к API: {str(e)}")
        raise Exception(f"Ошибка при взаимодействии с API: {str(e)}")

def process_request(chat_id):
    try:
        url = user_data[chat_id]['url']
        file_format = user_data[chat_id]['format']
        quality = user_data[chat_id].get('quality', 'best')
        username = user_data[chat_id]['username']
        
        headers = {"X-API-Key": ALLOWED_USERS[username]}
        data = {
            "url": url,
            "format": file_format,
            "quality": quality
        }
        
        response = requests.post(f"{API_BASE_URL}/download", json=data, headers=headers)
        response.raise_for_status()
        task_id = response.json()['task_id']
        bot.edit_message_text(f"Задача на загрузку создана. Ожидаем завершения...", chat_id, user_data[chat_id]['processing_message_id'])
        
        while True:
            status_response = requests.get(f"{API_BASE_URL}/status/{task_id}", headers=headers)
            status_response.raise_for_status()
            status_data = status_response.json()
            
            if status_data['status'] == 'completed':
                file_path = status_data['file']
                file_url = f"{API_BASE_URL}{file_path}"
                file_response = requests.get(file_url, headers=headers)
                file_response.raise_for_status()
                
                file_name = os.path.basename(file_path)
                with open(file_name, 'wb') as f:
                    f.write(file_response.content)
                
                with open(file_name, 'rb') as file:
                    if file_format == 'video':
                        bot.send_video(chat_id, file, caption="Ваше видео готово!", supports_streaming=True)
                    else:
                        bot.send_audio(chat_id, file, caption="Ваше аудио готово!")
                
                os.remove(file_name)
                break
            elif status_data['status'] == 'failed':
                raise Exception(f"Задача завершилась с ошибкой: {status_data.get('error', 'Неизвестная ошибка')}")
            
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

logger.info("Бот запущен")
bot.polling(none_stop=True, timeout=120)