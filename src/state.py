from config import BOT_TOKEN, API_BASE_URL, ADMIN_API_KEY
import telebot, yt_dlp_host_api

user_data = {}
bot = telebot.TeleBot(BOT_TOKEN)
api = yt_dlp_host_api.api(API_BASE_URL)
admin = api.get_client(ADMIN_API_KEY)
