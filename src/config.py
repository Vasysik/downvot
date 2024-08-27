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

config = load_config()
BOT_TOKEN = config['BOT_TOKEN']
API_BASE_URL = config['API_BASE_URL']
