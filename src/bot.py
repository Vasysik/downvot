import logging, time
from telebot.apihelper import ApiTelegramException
from config import load_config
from handlers import register_handlers
from state import bot

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

register_handlers(bot)

def main():
    restart_count = 0
    while True:
        try:
            logger.info(f"Starting bot polling. Restart count: {restart_count}")
            bot.polling(none_stop=True, interval=1, timeout=20)
        except ApiTelegramException as e:
            restart_count += 1
            logger.error(f"Telegram API error: {e}. Restarting bot. Restart count: {restart_count}")
            time.sleep(5)
        except Exception as e:
            restart_count += 1
            logger.error(f"Unexpected error: {e}. Restarting bot. Restart count: {restart_count}")
            time.sleep(5)

if __name__ == "__main__":
    config = load_config()
    logger.info("Bot initialized")
    main()