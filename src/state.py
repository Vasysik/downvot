import telebot
import yt_dlp_host_api
from config import BOT_TOKEN, API_BASE_URL

user_data = {}
bot = telebot.TeleBot(BOT_TOKEN)
api = yt_dlp_host_api.api(API_BASE_URL)
