from state import user_data
from youtube_search import YoutubeSearch
import utils, logging

logger = logging.getLogger(__name__)

def register_handlers(bot):
    @bot.message_handler(commands=['start'])
    @utils.authorized_users_only
    def start_message(message):
        logger.info(f"User {message.from_user.username} {user_data[message.chat.id]['language']} started the bot")
        bot.reply_to(message, utils.get_string("start_message", user_data[message.chat.id]['language']))
    
    @bot.message_handler(commands=['admin'])
    @utils.authorized_users_only
    def admin_panel(message):
        logger.info(f"User {message.from_user.username} requested the admin panel")
        client = user_data[message.chat.id]['client']
        
        if client.check_permissions(["create_key", "delete_key", "get_key", "get_keys"]):
            bot.reply_to(message, utils.get_string("admin_panel", user_data[message.chat.id]['language']), reply_markup=utils.admin_keyboard(user_data[message.chat.id]['language']))
        else:
            bot.reply_to(message, utils.get_string("no_admin_access", user_data[message.chat.id]['language']))

    @bot.message_handler(commands=['create_key'])
    @utils.authorized_users_only
    def create_key(message):
        logger.info(f"User {message.from_user.username} requested key creation")
        client = user_data[message.chat.id]['client']
        
        if client.check_permissions(["create_key"]):
            bot.reply_to(message, utils.get_string("enter_new_key_username", user_data[message.chat.id]['language']))
            bot.register_next_step_handler(message, utils.create_key_step)
        else:
            bot.reply_to(message, utils.get_string("no_key_creation_access", user_data[message.chat.id]['language']))

    @bot.message_handler(commands=['delete_key'])
    @utils.authorized_users_only
    def delete_key(message):
        logger.info(f"User {message.from_user.username} requested key deletion")
        client = user_data[message.chat.id]['client']
        
        if client.check_permissions(["delete_key"]):
            bot.reply_to(message, utils.get_string("enter_key_delete_username", user_data[message.chat.id]['language']))
            bot.register_next_step_handler(message, utils.delete_key_step)
        else:
            bot.reply_to(message, utils.get_string("no_key_deletion_access", user_data[message.chat.id]['language']))
    
    @bot.message_handler(commands=['help'])
    @utils.authorized_users_only
    def send_help(message):
        chat_id = message.chat.id
        bot.reply_to(message, utils.get_string('help_text', user_data[chat_id]['language']))

    @bot.message_handler(commands=['language'])
    @utils.authorized_users_only
    def language_command(message):
        chat_id = message.chat.id
        bot.reply_to(message, utils.get_string('select_language', user_data[chat_id]['language']), reply_markup=utils.language_keyboard())

    @bot.message_handler(commands=['download'])
    @utils.authorized_users_only
    def download_video(message):
        link = message.text[len('/download '):].strip()
        if not link:
            bot.reply_to(message, utils.get_string('send_video_link', user_data[chat_id]['language']))
            return
        
        source = utils.detect_source(link)
        if not source:
            bot.reply_to(message, utils.get_string('unknown_source', user_data[message.chat.id]['language']))
            return
        
        chat_id = message.chat.id
        processing_message = bot.reply_to(
            message,
            utils.get_string('source_detected', user_data[chat_id]['language']).format(source=source),
            reply_markup=utils.type_keyboard(user_data[chat_id]['language'])
        )
        processing_message_id = str(processing_message.message_id)
        user_data[chat_id][processing_message_id] = {
            'url': link,
            'source': source
        }

    @bot.message_handler(commands=['search'])
    @utils.authorized_users_only
    def search_videos(message):
        query = message.text[len('/search '):].strip()
        if not query:
            bot.reply_to(message, utils.get_string('enter_search_query', user_data[message.chat.id]['language']))
            return
        searching_message = bot.send_message(message.chat.id, utils.get_string('searching', user_data[message.chat.id]['language']))
        try:
            results = YoutubeSearch(query, max_results=20).to_dict()
            if not results:
                bot.edit_message_text(
                    utils.get_string('no_results', user_data[message.chat.id]['language']),
                    chat_id=message.chat.id,
                    message_id=searching_message.message_id
                )
                return
            user_data[message.chat.id]['search_results'] = results
            user_data[message.chat.id]['current_index'] = 0

            utils.show_search_result(message.chat.id, user_data[message.chat.id]['language'], 0, searching_message.message_id)
        except Exception as e:
            logger.error(f"Error during YouTube search: {e}")
            bot.edit_message_text(
                utils.get_string('search_error', user_data[message.chat.id]['language']).format(error=str(e)),
                chat_id=message.chat.id,
                message_id=searching_message.message_id
            )
    
    @bot.callback_query_handler(func=lambda call: call.data.startswith("admin_"))
    @utils.authorized_users_only
    def admin_callback_query(call):
        try:
            chat_id = call.message.chat.id

            if call.data == "admin_create_key":
                bot.edit_message_text(utils.get_string("enter_new_key_username", user_data[chat_id]['language']), chat_id, call.message.message_id)
                bot.register_next_step_handler(call.message, utils.create_key_step)

            elif call.data == "admin_delete_key":
                bot.edit_message_text(utils.get_string("enter_key_delete_username", user_data[chat_id]['language']), chat_id, call.message.message_id)
                bot.register_next_step_handler(call.message, utils.delete_key_step)
        except Exception as e:
            logger.error(f"Error processing request for user {chat_id}: {str(e)}")
            bot.send_message(chat_id, utils.get_string('processing_error', user_data[chat_id]['language']).format(error=str(e)), parse_mode='HTML')
    
    @bot.message_handler(func=lambda message: True)
    @utils.authorized_users_only
    def handle_message(message):
        if message.text.startswith(('http://', 'https://')):
            source = utils.detect_source(message.text)
            if source:
                logger.info(f"Received link from user {message.from_user.username}: {message.text}")
                processing_message = bot.reply_to(message, utils.get_string('source_detected', user_data[message.chat.id]['language']).format(source=source), reply_markup=utils.type_keyboard(user_data[message.chat.id]['language']))
                
                processing_message_id = str(processing_message.message_id)
                user_data[message.chat.id][processing_message_id] = {
                    'url': message.text,
                    'source': source
                }
            else:
                bot.reply_to(message, utils.get_string('unknown_source', user_data[message.chat.id]['language']))
        else:
            searching_message = bot.send_message(message.chat.id, utils.get_string('searching', user_data[message.chat.id]['language']))
            try:
                results = YoutubeSearch(message.text, max_results=20).to_dict()
                if not results:
                    bot.edit_message_text(
                        utils.get_string('no_results', user_data[message.chat.id]['language']),
                        chat_id=message.chat.id,
                        message_id=searching_message.message_id
                    )
                    return
                user_data[message.chat.id]['search_results'] = results
                user_data[message.chat.id]['current_index'] = 0

                utils.show_search_result(message.chat.id, user_data[message.chat.id]['language'], 0, searching_message.message_id)
            except Exception as e:
                logger.error(f"Error during YouTube search: {e}")
                bot.edit_message_text(
                    utils.get_string('search_error', user_data[message.chat.id]['language']).format(error=str(e)),
                    chat_id=message.chat.id,
                    message_id=searching_message.message_id
                )

    @bot.callback_query_handler(func=lambda call: call.data.startswith("lang_"))
    def callback_language(call):
        chat_id = call.message.chat.id
        lang_code = call.data.split("_")[1]
        user_data[chat_id]['language'] = lang_code
        bot.edit_message_text(utils.get_string('language_changed', lang_code), chat_id, call.message.message_id)

    def handle_start_time(message, processing_message_id):
        chat_id = message.chat.id
        message_id = message.message_id
        try:
            start_time_str = message.text.strip()
            if start_time_str == '-':
                start_time = None
            else:
                start_time = utils.parse_timestamp(start_time_str)
                video_duration = user_data[chat_id][processing_message_id]['file_info']['duration']
                if start_time >= video_duration:
                    raise ValueError("Start time cannot be greater than video duration")
            
            user_data[chat_id][processing_message_id]['start_time'] = start_time
            bot.edit_message_text(utils.get_string('enter_end_time', user_data[chat_id]['language']), chat_id, processing_message_id)
            bot.register_next_step_handler(message, handle_end_time, processing_message_id)
            
        except ValueError as e:
            bot.send_message(
                chat_id,
                utils.get_string('invalid_timestamp', user_data[chat_id]['language']).format(error=str(e))
            )
            bot.register_next_step_handler(message, handle_start_time, processing_message_id)
        bot.delete_message(chat_id, message_id)

    def handle_end_time(message, processing_message_id):
        message_id = message.message_id
        chat_id = message.chat.id
        try:
            end_time_str = message.text.strip()
            if end_time_str == '-':
                end_time = None
            else:
                end_time = utils.parse_timestamp(end_time_str)
                video_duration = user_data[chat_id][processing_message_id]['file_info']['duration']
                if end_time > video_duration:
                    end_time = video_duration
                
                start_time = user_data[chat_id][processing_message_id].get('start_time')
                if start_time is not None and end_time <= start_time:
                    raise ValueError("End time must be greater than start time")
            
            user_data[chat_id][processing_message_id]['end_time'] = end_time
            
            keyboard = utils.crop_keyboard(user_data[chat_id]['language'], processing_message_id)
            bot.edit_message_text(utils.get_string('select_crop_mode', user_data[chat_id]['language']), chat_id,processing_message_id, reply_markup=keyboard)
            
        except ValueError as e:
            bot.send_message(
                chat_id,
                utils.get_string('invalid_timestamp', user_data[chat_id]['language']).format(error=str(e))
            )
            bot.register_next_step_handler(message, handle_end_time, processing_message_id)
        bot.delete_message(chat_id, message_id)

    @bot.callback_query_handler(func=lambda call: True)
    @utils.authorized_users_only
    def callback_query(call):
        chat_id = call.message.chat.id
        processing_message_id = str(call.message.message_id)
        if not user_data[chat_id].get(processing_message_id): user_data[chat_id][processing_message_id] = {}

        try:
            if call.data.startswith("admin_"):
                admin_callback_query(call)
            elif call.data.startswith("type_"):
                user_data[chat_id][processing_message_id]['file_type'] = 'video' if call.data.split("_")[1] == 'video' else 'audio'
                bot.edit_message_text(utils.get_string('getting_video_info', user_data[chat_id]['language']), chat_id, processing_message_id)
                try:
                    client = user_data[chat_id]['client']
                    info = client.get_info(url=user_data[chat_id][processing_message_id]['url']).get_json(['qualities', 'title', 'thumbnail', 'is_live', 'duration'])
                    user_data[chat_id][processing_message_id]['file_info'] = info
                    if info['is_live'] == True:
                        bot.edit_message_text(utils.get_string('specify_recording_duration', user_data[chat_id]['language']), chat_id, processing_message_id, reply_markup=utils.duration_keyboard(user_data[chat_id]['language'], processing_message_id))
                    else:
                        available_qualities = info['qualities']
                        bot.edit_message_text(utils.get_string('select_quality', user_data[chat_id]['language']), chat_id, processing_message_id, reply_markup=utils.quality_keyboard(available_qualities, chat_id, processing_message_id))  
                except Exception as e:
                    logger.error(f"Error getting video information: {str(e)}")
                    bot.edit_message_text(utils.get_string('video_info_error', user_data[chat_id]['language']), chat_id, processing_message_id)
            elif call.data.startswith('duration_'):
                duration, processing_message_id = call.data.split('_')[1:]
                user_data[chat_id][processing_message_id]['duration'] = int(duration)
                available_qualities = user_data[chat_id][processing_message_id]['file_info']['qualities']
                bot.edit_message_text(utils.get_string('select_video_quality', user_data[chat_id]['language']), chat_id, processing_message_id, reply_markup=utils.quality_keyboard(available_qualities, chat_id, processing_message_id))
            elif call.data.startswith("select_video_quality_"):
                processing_message_id = call.data.split("_")[-1]
                available_qualities = user_data[chat_id][processing_message_id]['file_info']['qualities']
                bot.edit_message_text(utils.get_string('select_video_quality', user_data[chat_id]['language']), chat_id, processing_message_id, reply_markup=utils.video_quality_keyboard(available_qualities, processing_message_id))
            elif call.data.startswith("select_audio_quality_"):
                processing_message_id = call.data.split("_")[-1]
                available_qualities = user_data[chat_id][processing_message_id]['file_info']['qualities']
                bot.edit_message_text(utils.get_string('select_audio_quality', user_data[chat_id]['language']), chat_id, processing_message_id, reply_markup=utils.audio_quality_keyboard(available_qualities, processing_message_id))
            elif call.data.startswith("video_quality_"):
                quality, processing_message_id = call.data.split("_")[2:]
                user_data[chat_id][processing_message_id]['video_format'] = quality
                available_qualities = user_data[chat_id][processing_message_id]['file_info']['qualities']
                bot.edit_message_text(utils.get_string('select_quality', user_data[chat_id]['language']), chat_id, processing_message_id, reply_markup=utils.quality_keyboard(available_qualities, chat_id, processing_message_id, selected_video=quality, selected_audio=user_data[chat_id][processing_message_id].get('audio_format')))
            elif call.data.startswith("audio_quality_"):
                quality, processing_message_id = call.data.split("_")[2:]
                user_data[chat_id][processing_message_id]['audio_format'] = quality
                available_qualities = user_data[chat_id][processing_message_id]['file_info']['qualities']
                bot.edit_message_text(utils.get_string('select_quality', user_data[chat_id]['language']), chat_id, processing_message_id, reply_markup=utils.quality_keyboard(available_qualities, chat_id, processing_message_id, selected_video=user_data[chat_id][processing_message_id].get('video_format'), selected_audio=quality))
            elif call.data.startswith("back_to_main_"):
                processing_message_id = call.data.split("_")[-1]
                available_qualities = user_data[chat_id][processing_message_id]['file_info']['qualities']
                bot.edit_message_text(utils.get_string('select_quality', user_data[chat_id]['language']), chat_id, processing_message_id, reply_markup=utils.quality_keyboard(available_qualities, chat_id, processing_message_id, selected_video=user_data[chat_id][processing_message_id]['video_format'], selected_audio=user_data[chat_id][processing_message_id]['audio_format']))
            elif call.data.startswith("quality_"):
                processing_message_id, video_quality, audio_quality = call.data.split("_")[1:]
                user_data[chat_id][processing_message_id]['video_format'] = video_quality
                user_data[chat_id][processing_message_id]['audio_format'] = audio_quality
                utils.process_request(chat_id, processing_message_id)
                logger.info(f"Link from user {call.message.from_user.username} successfully processed!")
            elif call.data.startswith("crop_time_"):
                processing_message_id = call.data.split("_")[2]
                bot.edit_message_text(utils.get_string('enter_start_time', user_data[chat_id]['language']), chat_id, processing_message_id )
                bot.register_next_step_handler(call.message, handle_start_time, processing_message_id)
            elif call.data.startswith("crop_mode_"):
                processing_message_id = call.data.split("_")[2]
                crop_mode = call.data.split("_")[3]
                force_keyframes = (crop_mode == 'precise')
                user_data[chat_id][processing_message_id]['force_keyframes'] = force_keyframes
                available_qualities = user_data[chat_id][processing_message_id]['file_info']['qualities']
                bot.edit_message_text(utils.get_string('select_quality', user_data[chat_id]['language']), chat_id, processing_message_id, reply_markup=utils.quality_keyboard(available_qualities, chat_id, processing_message_id, selected_video=user_data[chat_id][processing_message_id]['video_format'], selected_audio=user_data[chat_id][processing_message_id]['audio_format']))
            elif call.data.startswith("prev_result_"):
                current_index = int(call.data.split("_")[-1])
                user_data[call.message.chat.id]['current_index'] = max(0, current_index - 1)
                utils.show_search_result(call.message.chat.id, user_data[chat_id]['language'], user_data[call.message.chat.id]['current_index'], call.message.message_id)
            elif call.data.startswith("next_result_"):
                current_index = int(call.data.split("_")[-1])
                user_data[call.message.chat.id]['current_index'] = min(len(user_data[call.message.chat.id]['search_results']) - 1, current_index + 1)
                utils.show_search_result(call.message.chat.id, user_data[chat_id]['language'], user_data[call.message.chat.id]['current_index'], call.message.message_id)
            elif call.data.startswith("select_result_"):
                index = int(call.data.split("_")[-1])
                result = user_data[call.message.chat.id]['search_results'][index]
                link = f"https://www.youtube.com{result['url_suffix']}"
                source = utils.detect_source(link)
                if source:
                    chat_id = call.message.chat.id
                    processing_message = bot.send_message(
                        chat_id,
                        utils.get_string('source_detected', user_data[chat_id]['language']).format(source=source),
                        reply_markup=utils.type_keyboard(user_data[chat_id]['language'])
                    )
                    processing_message_id = str(processing_message.message_id)
                    user_data[chat_id][processing_message_id] = { 'url': link, 'source': source }
                else:
                    bot.send_message(call.message.chat.id, utils.get_string('unknown_source', user_data[call.message.chat.id]['language']))
        
        except Exception as e:
            logger.error(f"Error processing callback query: {str(e)}")
            bot.send_message(chat_id, utils.get_string('processing_error', user_data[chat_id]['language']).format(error=str(e)), parse_mode='HTML')
