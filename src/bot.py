import logging
from config import load_config
from handlers import register_handlers
from state import bot

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

register_handlers(bot)

if __name__ == "__main__":
    config = load_config()
    logger.info("Bot started")
    bot.polling(none_stop=True)
