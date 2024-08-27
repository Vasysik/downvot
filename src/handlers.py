from config import load_config, API_BASE_URL
from state import user_data
import utils, logging, requests

logger = logging.getLogger(__name__)

def register_handlers(bot):
    @bot.message_handler(commands=['start'])
    @utils.authorized_users_only
    def start_message(message):
        logger.info(f"Пользователь {message.from_user.username} запустил бота")
        bot.reply_to(message, "Здравствуйте. Я бот для загрузки медиафайлов.\nПожалуйста, отправьте ссылку на YouTube видео.")
    
    @bot.message_handler(commands=['admin'])
    @utils.authorized_users_only
    def admin_panel(message):
        username = str(message.from_user.username)
        logger.info(f"Пользователь {username} запустил админ панель")
        headers = {"X-API-Key": load_config()['ALLOWED_USERS'][username]}
        
        response = requests.post(f"{API_BASE_URL}/permissions_check", json={"permissions": ["admin"]}, headers=headers)
        
        if response.status_code == 200:
            bot.reply_to(message, "Админ панель:", reply_markup=utils.admin_keyboard())
        else:
            bot.reply_to(message, "Извините, у вас нет доступа к админ панели.")
    
    @bot.callback_query_handler(func=lambda call: call.data.startswith("admin_"))
    def admin_callback_query(call):
        chat_id = call.message.chat.id
        username = str(call.from_user.username)

        if call.data == "admin_list_keys":
            config = load_config()
            keys = config['ALLOWED_USERS']
            key_list = "Список ключей:\n\n"
            for user, key in keys.items():
                key_list += f"Пользователь: {user}\n"
                key_list += f"Ключ: <tg-spoiler>{key}</tg-spoiler>\n\n"
            bot.send_message(chat_id, key_list, parse_mode='HTML')

        elif call.data == "admin_create_key":
            bot.send_message(chat_id, "Введите имя пользователя для нового ключа:")
            bot.register_next_step_handler(call.message, utils.create_key_step)

        elif call.data == "admin_delete_key":
            bot.send_message(chat_id, "Введите имя пользователя, чей ключ нужно удалить:")
            bot.register_next_step_handler(call.message, utils.delete_key_step)

    @bot.message_handler(func=lambda message: True)
    @utils.authorized_users_only
    def handle_message(message):
        if message.text.startswith(('http://', 'https://')):
            source = utils.detect_source(message.text)
            if source:
                logger.info(f"Получена ссылка от пользователя {message.from_user.username}: {message.text}")
                user_data[message.chat.id] = {'url': message.text, 'username': message.from_user.username, 'source': source}
                bot.reply_to(message, f"Обнаружен сервис: {source}.\nВыберите формат для сохранения:", reply_markup=utils.format_keyboard())
            else:
                bot.reply_to(message, "Извините, я не могу определить источник по этой ссылке.\nПожалуйста, убедитесь, что вы отправили корректную ссылку.")
        else:
            bot.reply_to(message, "Пожалуйста, отправьте ссылку на видео.")

    @bot.callback_query_handler(func=lambda call: True)
    def callback_query(call):
        chat_id = call.message.chat.id
        if call.data.startswith("admin_"):
            admin_callback_query(call)
        elif call.data.startswith("format_"):
            user_data[chat_id]['format'] = 'video' if call.data.split("_")[1] == 'video' else 'audio'
            bot.edit_message_text("Получение информации о видео.\nПожалуйста, подождите.", chat_id, call.message.message_id)
            try:
                info = utils.get_info(user_data[chat_id]['url'], user_data[chat_id]['username'], '?qualities&title')
                user_data[chat_id]['file_info'] = info
                if user_data[chat_id]['format'] == 'video':
                    available_qualities = info['qualities']
                    user_data[chat_id]['available_qualities'] = available_qualities
                    bot.edit_message_text("Выберите качество видео:", chat_id, call.message.message_id, reply_markup=utils.quality_keyboard(available_qualities))  
                else:
                    message = bot.edit_message_text("Начинаю обработку запроса.\nПожалуйста, подождите.", chat_id, call.message.message_id)
                    user_data[chat_id]['processing_message_id'] = message.message_id
                    utils.process_request(chat_id)
            except Exception as e:
                logger.error(f"Ошибка при получении информации о видео: {str(e)}")
                bot.edit_message_text("Произошла ошибка при получении информации о видео.\nПожалуйста, попробуйте еще раз.", chat_id, call.message.message_id)
        elif call.data.startswith("quality_"):
            user_data[chat_id]['quality'] = call.data.split("_")[1]
            message = bot.edit_message_text("Начинаю обработку запроса.\nПожалуйста, подождите.", chat_id, call.message.message_id)
            user_data[chat_id]['processing_message_id'] = message.message_id
            utils.process_request(chat_id)
