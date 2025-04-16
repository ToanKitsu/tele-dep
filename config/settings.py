# config/settings.py
import os
import logging
# import json # No longer needed
from dotenv import load_dotenv
# from cryptography.fernet import Fernet # No longer needed

load_dotenv() # Load .env first

logger = logging.getLogger(__name__)

# --- Helper function to get environment variables ---
def get_env_var(var_name, default=None, required=True, var_type=str):
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
                        processed_items.append(item) # Keep as string if not int
                return processed_items
            # Removed JSON ABI loading logic here
            return var_type(value)
        except ValueError as e:
            logger.error(f"ERROR: Invalid type for environment variable '{var_name}'. Expected {var_type}. Got '{value}'. Error: {e}")
            raise ValueError(f"Invalid type for environment variable: {var_name}") from e
    if not required and value is None:
        return default
    return value # Return processed value (could be None if not required)

# --- Removed JSON file loading helper ---

# --- Paths ---
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# CONTRACTS_DIR removed

# --- Telegram API (From .env) ---
API_ID = get_env_var('API_ID', required=True, var_type=int)
API_HASH = get_env_var('API_HASH', required=True)
PHONE_NUMBER = get_env_var('PHONE_NUMBER', required=True)
BOT_TOKEN = get_env_var('BOT_TOKEN', required=True)

# --- Bot Configuration (From .env) ---
SOURCE_BOT_IDENTIFIER = get_env_var('SOURCE_BOT_IDENTIFIER', required=True, var_type=int)
TARGET_CHAT_IDS = get_env_var('TARGET_CHAT_IDS', required=True, var_type=list)
if not TARGET_CHAT_IDS:
    logger.error("ERROR: TARGET_CHAT_IDS is required and cannot be empty.")
    raise ValueError("TARGET_CHAT_IDS cannot be empty.")

SESSION_NAME = get_env_var('SESSION_NAME', default='my_telegram_user_session')
BUTTON_TEXT_TO_FIND = get_env_var('BUTTON_TEXT_TO_FIND', default="View Tweet") # Essential for filtering
MAX_CONCURRENT_TASKS = get_env_var('MAX_CONCURRENT_TASKS', default=5, var_type=int) # Used for batch sending
LOG_LEVEL = get_env_var('LOG_LEVEL', default='INFO').upper()

# --- Removed Blockchain Settings ---
# MASTER_ENCRYPTION_KEY, FERNET, NETWORKS, get_network_config removed
# --- Removed Contract Settings ---
# ERC20_BYTECODE, ERC20_ABI, UNISWAPV2_ROUTER_ABI removed

# --- Removed Bot Logic Settings (Blockchain related) ---
# MAX_WALLETS_PER_USER, DEFAULT_BUY_GAS_LIMIT, ADD_LIQUIDITY_DELAY_SECONDS, WALLET_STORAGE_FILE removed

# --- Telethon Internal (Keep if they help stability) ---
TELETHON_SYSTEM_VERSION = "4.16.30-vxCUSTOM"
TELETHON_DEVICE_MODEL = "Desktop"
TELETHON_CONNECTION_RETRIES = 5
TELETHON_AUTO_RECONNECT = True

# --- Removed get_network_config helper ---

logger.info("Core configuration loaded successfully (Blockchain features disabled).")