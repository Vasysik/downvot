from state import user_data
import utils, logging

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
        logger.info(f"Пользователь {message.from_user.username} запросил админ панель")
        client = user_data[message.chat.id]['client']
        
        if client.check_permissions(["create_key", "delete_key", "get_key", "get_keys"]):
            bot.reply_to(message, "Админ панель:", reply_markup=utils.admin_keyboard())
        else:
            bot.reply_to(message, "Извините, у вас нет доступа к админ панели.")

    @bot.message_handler(commands=['create_key'])
    @utils.authorized_users_only
    def create_key(message):
        logger.info(f"Пользователь {message.from_user.username} запросил создание ключа")
        client = user_data[message.chat.id]['client']
        
        if client.check_permissions(["create_key"]):
            bot.reply_to(message, "Введите имя пользователя для нового ключа:")
            bot.register_next_step_handler(message, utils.create_key_step)
        else:
            bot.reply_to(message, "Извините, у вас нет доступа к созданию ключей.")

    @bot.message_handler(commands=['delete_key'])
    @utils.authorized_users_only
    def delete_key(message):
        logger.info(f"Пользователь {message.from_user.username} запросил удаление ключа")
        client = user_data[message.chat.id]['client']
        
        if client.check_permissions(["delete_key"]):
            bot.reply_to(message, "Введите имя пользователя, чей ключ нужно удалить:")
            bot.register_next_step_handler(message, utils.delete_key_step)
        else:
            bot.reply_to(message, "Извините, у вас нет доступа к удалению ключей.")
    
    @bot.callback_query_handler(func=lambda call: call.data.startswith("admin_"))
    @utils.authorized_users_only
    def admin_callback_query(call):
        try:
            chat_id = call.message.chat.id

            # Unsafe
            # if call.data == "admin_list_keys":
            #     bot.edit_message_text(utils.list_keys(call.message), chat_id, call.message.message_id, parse_mode='HTML')

            if call.data == "admin_create_key":
                bot.edit_message_text("Введите имя пользователя для нового ключа:", chat_id, call.message.message_id)
                bot.register_next_step_handler(call.message, utils.create_key_step)

            elif call.data == "admin_delete_key":
                bot.edit_message_text("Введите имя пользователя, чей ключ нужно удалить:", chat_id, call.message.message_id)
                bot.register_next_step_handler(call.message, utils.delete_key_step)
        except Exception as e:
            logger.error(f"Ошибка при обработке запроса для пользователя {chat_id}: {str(e)}")
            bot.send_message(chat_id, f"Произошла ошибка при обработке запроса:\n<code>{str(e)}</code>", parse_mode='HTML')
        

    @bot.message_handler(func=lambda message: True)
    @utils.authorized_users_only
    def handle_message(message):
        if message.text.startswith(('http://', 'https://')):
            source = utils.detect_source(message.text)
            if source:
                logger.info(f"Получена ссылка от пользователя {message.from_user.username}: {message.text}")
                user_data[message.chat.id]['url'] = message.text
                user_data[message.chat.id]['source'] = source

                bot.reply_to(message, f"Обнаружен сервис: {source}.\nВыберите формат для сохранения:", reply_markup=utils.type_keyboard())
            else:
                bot.reply_to(message, "Извините, я не могу определить источник по этой ссылке.\nПожалуйста, убедитесь, что вы отправили корректную ссылку.")
        else:
            bot.reply_to(message, "Пожалуйста, отправьте ссылку на видео.")

    @bot.callback_query_handler(func=lambda call: True)
    @utils.authorized_users_only
    def callback_query(call):
        chat_id = call.message.chat.id
        if call.data.startswith("admin_"):
            admin_callback_query(call)
        elif call.data.startswith("type_"):
            user_data[chat_id]['file_type'] = 'video' if call.data.split("_")[1] == 'video' else 'audio'
            bot.edit_message_text("Получение информации о видео.\nПожалуйста, подождите.", chat_id, call.message.message_id)
            try:
                client = user_data[chat_id]['client']
                info = client.get_info(url=user_data[chat_id]['url']).get_json(['qualities', 'title', 'thumbnail'])
                user_data[chat_id]['file_info'] = info
                if user_data[chat_id]['file_type'] == 'video':
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
            logger.info(f"Cсылка от пользователя {message.from_user.username} успешно обработана!")
