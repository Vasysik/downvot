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

# --- Main Bot and API Config ---
BOT_TOKEN = config['BOT_TOKEN']
API_BASE_URL = config['API_BASE_URL']
ADMIN_API_KEY = config['ADMIN_API_KEY']
TELEGRAM_API_URL = config.get('TELEGRAM_API_URL', '')

# --- Access Control Config ---
access_config = config.get('ACCESS_CONTROL', {})
ALLOWED_USERS = access_config.get('ALLOWED_USERS', [])
PREMIUM_USERS = access_config.get('PREMIUM_USERS', [])
AUTO_ALLOWED_CHANNEL = access_config.get('AUTO_ALLOWED_CHANNEL', '')
AUTO_CREATE_KEY = access_config.get('AUTO_CREATE_KEY', True)
FILE_LINK_BUTTON_POLICY = access_config.get('FILE_LINK_BUTTON_POLICY', 'premium') # 'all', 'premium', 'none'

# --- Bot Behavior Settings ---
settings_config = config.get('BOT_SETTINGS', {})
DEFAULT_LANGUAGE = settings_config.get('DEFAULT_LANGUAGE', 'ru')
MAX_GET_RESULT_RETRIES = settings_config.get('MAX_GET_RESULT_RETRIES', 480)
MAX_SEARCH_RESULTS = settings_config.get('MAX_SEARCH_RESULTS', 50)
MAX_FILE_SIZE_MB = settings_config.get('MAX_FILE_SIZE_MB', 50)
MAX_TELEGRAM_FILE_SIZE = MAX_FILE_SIZE_MB * 1024 * 1024

LANGUAGES = {
    'en': load_language('en'),
    'ru': load_language('ru'),
    'pl': load_language('pl')
}
