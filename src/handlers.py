from state import user_data
import utils, logging

logger = logging.getLogger(__name__)

def register_handlers(bot):
    @bot.message_handler(commands=['start'])
    @utils.authorized_users_only
    def start_message(message):
        logger.info(f"Пользователь {message.from_user.username} {user_data[message.chat.id]['language']} запустил бота")
        bot.reply_to(message, utils.get_string("start_message", user_data[message.chat.id]['language']))
    
    @bot.message_handler(commands=['admin'])
    @utils.authorized_users_only
    def admin_panel(message):
        logger.info(f"Пользователь {message.from_user.username} запросил админ панель")
        client = user_data[message.chat.id]['client']
        
        if client.check_permissions(["create_key", "delete_key", "get_key", "get_keys"]):
            bot.reply_to(message, utils.get_string("admin_panel", user_data[message.chat.id]['language']), reply_markup=utils.admin_keyboard(user_data[message.chat.id]['language']))
        else:
            bot.reply_to(message, utils.get_string("no_admin_access", user_data[message.chat.id]['language']))

    @bot.message_handler(commands=['create_key'])
    @utils.authorized_users_only
    def create_key(message):
        logger.info(f"Пользователь {message.from_user.username} запросил создание ключа")
        client = user_data[message.chat.id]['client']
        
        if client.check_permissions(["create_key"]):
            bot.reply_to(message, utils.get_string("enter_new_key_username", user_data[message.chat.id]['language']))
            bot.register_next_step_handler(message, utils.create_key_step)
        else:
            bot.reply_to(message, utils.get_string("no_key_creation_access", user_data[message.chat.id]['language']))

    @bot.message_handler(commands=['delete_key'])
    @utils.authorized_users_only
    def delete_key(message):
        logger.info(f"Пользователь {message.from_user.username} запросил удаление ключа")
        client = user_data[message.chat.id]['client']
        
        if client.check_permissions(["delete_key"]):
            bot.reply_to(message, utils.get_string("enter_key_delete_username", user_data[message.chat.id]['language']))
            bot.register_next_step_handler(message, utils.delete_key_step)
        else:
            bot.reply_to(message, utils.get_string("no_key_deletion_access", user_data[message.chat.id]['language']))
    
    @bot.message_handler(commands=['language'])
    @utils.authorized_users_only
    def language_command(message):
        chat_id = message.chat.id
        bot.reply_to(message, utils.get_string('select_language', user_data[chat_id]['language']), reply_markup=utils.language_keyboard())
    
    @bot.callback_query_handler(func=lambda call: call.data.startswith("admin_"))
    @utils.authorized_users_only
    def admin_callback_query(call):
        try:
            chat_id = call.message.chat.id

            # Unsafe
            # if call.data == "admin_list_keys":
            #     bot.edit_message_text(utils.list_keys(call.message), chat_id, call.message.message_id, parse_mode='HTML')

            if call.data == "admin_create_key":
                bot.edit_message_text(utils.get_string("enter_new_key_username", user_data[chat_id]['language']), chat_id, call.message.message_id)
                bot.register_next_step_handler(call.message, utils.create_key_step)

            elif call.data == "admin_delete_key":
                bot.edit_message_text(utils.get_string("enter_key_delete_username", user_data[chat_id]['language']), chat_id, call.message.message_id)
                bot.register_next_step_handler(call.message, utils.delete_key_step)
        except Exception as e:
            logger.error(f"Ошибка при обработке запроса для пользователя {chat_id}: {str(e)}")
            bot.send_message(chat_id, utils.get_string('processing_error', user_data[chat_id]['language']).format(error=str(e)), parse_mode='HTML')

    @bot.message_handler(func=lambda message: True)
    @utils.authorized_users_only
    def handle_message(message):
        if message.text.startswith(('http://', 'https://')):
            source = utils.detect_source(message.text)
            if source:
                logger.info(f"Получена ссылка от пользователя {message.from_user.username}: {message.text}")
                user_data[message.chat.id]['url'] = message.text
                user_data[message.chat.id]['source'] = source

                bot.reply_to(message, utils.get_string('source_detected', user_data[message.chat.id]['language']).format(source=source), reply_markup=utils.type_keyboard(user_data[message.chat.id]['language']))
            else:
                bot.reply_to(message, utils.get_string('unknown_source', user_data[message.chat.id]['language']))
        else:
            bot.reply_to(message, utils.get_string('send_video_link', user_data[message.chat.id]['language']))

    @bot.callback_query_handler(func=lambda call: call.data.startswith('duration_'))
    def handle_duration(call):
        chat_id = call.message.chat.id
        info = user_data[chat_id]['file_info']
        duration = int(call.data.split('_')[1])
        user_data[chat_id]['duration'] = duration
        if user_data[chat_id]['file_type'] == 'video':
            available_qualities = info['qualities']
            bot.edit_message_text(utils.get_string('select_video_quality', user_data[chat_id]['language']), chat_id, call.message.message_id, reply_markup=utils.quality_keyboard(available_qualities))
        else:
            user_data[chat_id]['processing_message_id'] = call.message.message_id
            utils.process_request(chat_id)

    @bot.callback_query_handler(func=lambda call: call.data.startswith("lang_"))
    def callback_language(call):
        chat_id = call.message.chat.id
        lang_code = call.data.split("_")[1]
        user_data[chat_id]['language'] = lang_code
        bot.edit_message_text(utils.get_string('language_changed', lang_code), chat_id, call.message.message_id)

    @bot.callback_query_handler(func=lambda call: True)
    @utils.authorized_users_only
    def callback_query(call):
        chat_id = call.message.chat.id
        if call.data.startswith("admin_"):
            admin_callback_query(call)
        elif call.data.startswith("type_"):
            user_data[chat_id]['file_type'] = 'video' if call.data.split("_")[1] == 'video' else 'audio'
            bot.edit_message_text(utils.get_string('getting_video_info', user_data[chat_id]['language']), chat_id, call.message.message_id)
            try:
                client = user_data[chat_id]['client']
                info = client.get_info(url=user_data[chat_id]['url']).get_json(['qualities', 'title', 'thumbnail', 'is_live'])
                user_data[chat_id]['file_info'] = info
                if info['is_live'] == True:
                    bot.edit_message_text(utils.get_string('specify_recording_duration', user_data[chat_id]['language']), chat_id, call.message.message_id, reply_markup=utils.duration_keyboard(user_data[chat_id]['language']))
                elif user_data[chat_id]['file_type'] == 'video':
                    available_qualities = info['qualities']
                    bot.edit_message_text(utils.get_string('select_video_quality', user_data[chat_id]['language']), chat_id, call.message.message_id, reply_markup=utils.quality_keyboard(available_qualities))  
                else:
                    user_data[chat_id]['processing_message_id'] = call.message.message_id
                    utils.process_request(chat_id)
            except Exception as e:
                logger.error(f"Ошибка при получении информации о видео: {str(e)}")
                bot.edit_message_text(utils.get_string('video_info_error', user_data[chat_id]['language']), chat_id, call.message.message_id)
        elif call.data.startswith("quality_"):
            user_data[chat_id]['video_quality'] = call.data.split("_")[1]
            user_data[chat_id]['processing_message_id'] = call.message.message_id
            utils.process_request(chat_id)
            logger.info(f"Cсылка от пользователя {call.message.from_user.username} успешно обработана!")
