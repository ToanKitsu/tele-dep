# config/settings.py
import os
import logging
from dotenv import load_dotenv

load_dotenv() # Load .env first

logger = logging.getLogger(__name__)

# --- Helper function get_env_var (remains the same) ---
def get_env_var(var_name, default=None, required=True, var_type=str):
    # ... (implementation remains the same) ...
    value = os.getenv(var_name, default)
    if required and value is None:
        logger.error(f"ERROR: Environment variable '{var_name}' is not set.")
        raise ValueError(f"Missing required environment variable: {var_name}")
    if value is not None:
        try:
            if var_type == bool:
                return value.lower() in ('true', '1', 't', 'yes', 'y')
            elif var_type == list:
                # Split string into list (supports int or string items)
                items = [item.strip() for item in value.split(',') if item.strip()]
                processed_items = []
                for item in items:
                    try:
                        processed_items.append(int(item))
                    except ValueError:
                        # If conversion to int fails, log a warning but keep it if it's just a string?
                        # Or strictly enforce integers for chat IDs? Let's enforce.
                        logger.warning(f"Non-integer value '{item}' found in list variable '{var_name}', skipping.")
                        # processed_items.append(item) # Keep as string if not int
                return processed_items
            # Removed JSON ABI loading logic here
            return var_type(value)
        except ValueError as e:
            logger.error(f"ERROR: Invalid type for environment variable '{var_name}'. Expected {var_type}. Got '{value}'. Error: {e}")
            raise ValueError(f"Invalid type for environment variable: {var_name}") from e
    # If not required and value is None, return the default
    # This path is taken if required=False and the var is not set
    if not required and value is None:
        return default
    # If required and value is None, the error was already raised above.
    # If value is not None, return the processed value.
    return value # Return processed value (could be None if not required & not set)


# --- Paths ---
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# --- Telegram API (From .env) ---
API_ID = get_env_var('API_ID', required=True, var_type=int)
API_HASH = get_env_var('API_HASH', required=True)
PHONE_NUMBER = get_env_var('PHONE_NUMBER', required=True)
BOT_TOKEN = get_env_var('BOT_TOKEN', required=True)

# --- Bot Configuration (From .env) ---
SOURCE_BOT_IDENTIFIER = get_env_var('SOURCE_BOT_IDENTIFIER', required=True, var_type=int)
# ---> Make TARGET_CHAT_IDS optional, default to empty list <---
# This list from .env will only be used if target_groups.json doesn't exist on first load.
TARGET_CHAT_IDS_FROM_ENV = get_env_var('TARGET_CHAT_IDS', required=False, var_type=list, default=[])
#<---

SESSION_NAME = get_env_var('SESSION_NAME', default='my_telegram_user_session')
BUTTON_TEXT_TO_FIND = get_env_var('BUTTON_TEXT_TO_FIND', default="View Tweet") # Essential for filtering
MAX_CONCURRENT_TASKS = get_env_var('MAX_CONCURRENT_TASKS', default=5, var_type=int) # Used for batch sending
LOG_LEVEL = get_env_var('LOG_LEVEL', default='INFO').upper()

# --- Telethon Internal (Keep if they help stability) ---
TELETHON_SYSTEM_VERSION = "4.16.30-vxCUSTOM"
TELETHON_DEVICE_MODEL = "Desktop"
TELETHON_CONNECTION_RETRIES = 5
TELETHON_AUTO_RECONNECT = True

logger.info("Core configuration loaded successfully.")
# logger.info(f"Initial target groups from .env (used only if JSON is missing): {TARGET_CHAT_IDS_FROM_ENV}") # Optional debug log