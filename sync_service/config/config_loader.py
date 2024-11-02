import yaml
import logging
import sys

def load_config(config_path):
    try:
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)
            
        # Set up logging level from config
        log_level = config.get('settings', {}).get('log_level', 'INFO')
        logging.getLogger().setLevel(getattr(logging, log_level))
            
        return config
    except Exception as e:
        logging.error(f"Error loading config file {config_path}: {e}")
        sys.exit(1)
