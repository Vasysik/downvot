import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import json
import os
import logging
import random
import string
import requests
import re
import yt_dlp

logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

with open('config.json') as config_file:
    config = json.load(config_file)
    BOT_TOKEN = config['BOT_TOKEN']
    PROXY = config['PROXY']

bot = telebot.TeleBot(BOT_TOKEN)

user_data = {}

DOWNLOAD_FOLDER = 'downloads'
if not os.path.exists(DOWNLOAD_FOLDER):
    os.makedirs(DOWNLOAD_FOLDER)

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
    logger.info(f"Пользователь {message.from_user.id} запустил бота")
    bot.reply_to(message, "Здравствуйте. Я бот для загрузки медиафайлов. Пожалуйста, отправьте ссылку на видео или аудио.")

@bot.message_handler(func=lambda message: True)
def handle_message(message):
    if message.text.startswith(('http://', 'https://')):
        logger.info(f"Получена ссылка от пользователя {message.from_user.id}: {message.text}")
        source = detect_source(message.text)
        if source:
            user_data[message.chat.id] = {'url': message.text, 'source': source}
            bot.reply_to(message, f"Обнаружен сервис: {source}.\nВыберите формат для сохранения:", reply_markup=format_keyboard())
        else:
            bot.reply_to(message, "Извините, я не могу определить источник по этой ссылке. Пожалуйста, убедитесь, что вы отправили корректную ссылку на YouTube или Spotify.")
    else:
        bot.reply_to(message, "Пожалуйста, отправьте ссылку на видео или аудио.")

def detect_source(url):
    youtube_patterns = [r'(?:https?:\/\/)?(?:www\.)?(?:youtube\.com|youtu\.be)\/']
    spotify_patterns = [r'(?:https?:\/\/)?(?:open\.)?spotify\.com\/']

    for pattern in youtube_patterns:
        if re.search(pattern, url):
            return 'YouTube'
    
    for pattern in spotify_patterns:
        if re.search(pattern, url):
            return 'Spotify'
    
    return None

@bot.callback_query_handler(func=lambda call: True)
def callback_query(call):
    chat_id = call.message.chat.id
    if call.data.startswith("format_"):
        user_data[chat_id]['format'] = 'видео' if call.data.split("_")[1] == 'video' else 'аудио'
        if user_data[chat_id]['format'] == 'видео':
            bot.edit_message_text("Получение доступного качества. Пожалуйста, подождите.", chat_id, call.message.message_id)
            try:
                available_qualities = get_available_qualities(user_data[chat_id]['url'])
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

def process_request(chat_id):
    try:
        url = user_data[chat_id]['url']
        source = user_data[chat_id]['source']
        file_format = user_data[chat_id]['format']
        quality = user_data[chat_id].get('quality', 'best')
        
        logger.info(f"Обработка запроса для пользователя {chat_id}: {source}, {file_format}, {quality}")
        
        file_info = download_file(url, source, file_format, quality)
        
        if file_info:
            temp_file_path = file_info
            file_size = os.path.getsize(temp_file_path)
            
            if file_size > 50 * 1024 * 1024:  # если файл больше 50 МБ
                bot.send_message(chat_id, "Файл слишком большой для отправки. Попробуйте выбрать меньшее качество.")
            else:
                with open(temp_file_path, 'rb') as file:
                    caption = "Ваше видео готово!" if file_format.lower() == 'видео' else "Ваше аудио готово!"
                    try:
                        if file_format.lower() == 'видео':
                            bot.send_video(chat_id, file, caption=caption, supports_streaming=True, timeout=60)
                        else:
                            bot.send_audio(chat_id, file, caption=caption, timeout=60)
                        logger.info(f"Файл успешно отправлен пользователю {chat_id}")
                    except telebot.apihelper.ApiTelegramException as e:
                        if "Request Entity Too Large" in str(e):
                            bot.send_message(chat_id, "Файл слишком большой для отправки. Попробуйте выбрать меньшее качество.")
                        else:
                            raise
            
            os.remove(temp_file_path)
        else:
            logger.error(f"Ошибка при скачивании файла для пользователя {chat_id}")
            bot.send_message(chat_id, "К сожалению, произошла ошибка при обработке запроса. Пожалуйста, попробуйте еще раз или проверьте корректность ссылки.")
    except Exception as e:
        logger.error(f"Ошибка при обработке запроса для пользователя {chat_id}: {str(e)}")
        bot.send_message(chat_id, f"Произошла ошибка при обработке запроса. Пожалуйста, попробуйте еще раз позже.")
    finally:
        if 'processing_message_id' in user_data.get(chat_id, {}):
            try:
                bot.delete_message(chat_id, user_data[chat_id]['processing_message_id'])
            except Exception as e:
                logger.error(f"Не удалось удалить сообщение о обработке: {str(e)}")
        
        if chat_id in user_data:
            del user_data[chat_id]
    
    bot.send_message(chat_id, "Если у вас есть еще запросы, пожалуйста, отправьте новую ссылку.")

def download_file(url, source, file_format, quality):
    if source == 'YouTube':
        return download_youtube(url, file_format, quality)
    elif source == 'Spotify':
        return download_spotify(url, file_format)
    else:
        return None

def get_available_qualities(url):
    ydl_opts = {'quiet': True, 'no_warnings': True}

    if PROXY:
        ydl_opts['proxy'] = PROXY
        logger.info(f"Используется прокси: {PROXY}")
    else:
        logger.info("Прокси не используется")
    
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)
        formats = info['formats']
        qualities = set()
        for f in formats:
            if f.get('height'):
                qualities.add(f'{f["height"]}p')
    return sorted(list(qualities), key=lambda x: int(x[:-1]))

def download_youtube(url, file_format, quality):
    try:
        random_string = ''.join(random.choices(string.ascii_letters + string.digits, k=8))
        output_template = os.path.join(DOWNLOAD_FOLDER, f'%(title)s_{random_string}_DownVot_{quality}.%(ext)s')

        if file_format.lower() == 'аудио':
            ydl_opts = {
                'format': 'bestaudio/best',
                'outtmpl': output_template,
                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': '192',
                }],
            }
        else:
            ydl_opts = {
                'format': f'bestvideo[height<={quality[:-1]}]+bestaudio/best',
                'outtmpl': output_template,
                'merge_output_format': 'mp4',
            }

            if PROXY:
                ydl_opts['proxy'] = PROXY
                logger.info(f"Используется прокси: {PROXY}")
            else:
                logger.info("Прокси не используется")

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)
            if file_format.lower() == 'аудио':
                filename = filename.rsplit('.', 1)[0] + '.mp3'
            else:
                filename = filename.rsplit('.', 1)[0] + '.mp4'

        clean_name = re.sub(r'[^a-zA-Z0-9_.]', '', os.path.basename(filename))
        clean_name = re.sub(r'\s+', '_', clean_name)
        new_filename = os.path.join(os.path.dirname(filename), clean_name)
        os.rename(filename, new_filename)

        logger.info(f"Файл с YouTube успешно скачан: {new_filename}")
        return new_filename
    except Exception as e:
        logger.error(f"Ошибка при скачивании с YouTube: {str(e)}")
        raise

def download_spotify(url, file_format):
    logger.info(f"Попытка скачать с Spotify: {url} ({file_format})")
    return None

logger.info("Бот запущен")
bot.polling(none_stop=True, timeout=120)