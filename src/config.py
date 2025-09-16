import json
import os

def load_config():
    config_path = os.path.join(os.path.dirname(__file__), '..', 'config.json')
    with open(config_path, 'r') as config_file:
        return json.load(config_file)

def save_config(config):
    config_path = os.path.join(os.path.dirname(__file__), '..', 'config.json')
    with open(config_path, 'w') as config_file:
        json.dump(config, config_file, indent=4)

def load_language(lang_code):
    lang_path = os.path.join(os.path.dirname(__file__), '..', 'lang_files', f'{lang_code}.json')
    with open(lang_path, 'r', encoding='utf-8') as lang_file:
        return json.load(lang_file)

config = load_config()
BOT_TOKEN = config['BOT_TOKEN']
API_BASE_URL = config['API_BASE_URL']
ADMIN_API_KEY = config['ADMIN_API_KEY']
AUTO_CREATE_KEY = config['AUTO_CREATE_KEY']
AUTO_ALLOWED_CHANNEL = config['AUTO_ALLOWED_CHANNEL']
DEFAULT_LANGUAGE = config['DEFAULT_LANGUAGE']
MAX_GET_RESULT_RETRIES = config['MAX_GET_RESULT_RETRIES']
MAX_SEARCH_RESULTS = config['MAX_SEARCH_RESULTS']
MAX_TELEGRAM_FILE_SIZE = 50 * 1024 * 1024
LANGUAGES = {
    'en': load_language('en'),
    'ru': load_language('ru'),
    'pl': load_language('pl')
}
