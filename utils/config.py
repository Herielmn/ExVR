from copy import deepcopy

from utils.json_manager import load_json, save_json

def setup_config():
    config = load_json("settings/config.json")
    return config

def save_config(config):
    config = deepcopy(config)
    save_json(config, "settings/config.json")


def save_setting(key, value):
    stored = load_json("settings/config.json")
    setting = stored.get("Setting") if isinstance(stored, dict) else None
    if not isinstance(setting, dict) or setting.get(key) == value:
        return
    setting[key] = value
    save_json(stored, "settings/config.json")
