# config/group_config.py
import logging
from collections import defaultdict

logger = logging.getLogger(__name__)

# In-memory storage for group settings. Key: chat_id (int), Value: mode (str: 'full' or 'fxtwitter')
# defaultdict ensures that if a group hasn't been configured, it defaults to 'full'.
_group_settings = defaultdict(lambda: 'full')

# Define modes
MODE_FULL = 'full'
MODE_FXTWITTER = 'fxtwitter'
VALID_MODES = {MODE_FULL, MODE_FXTWITTER}

def set_group_mode(chat_id: int, mode: str):
    """Sets the forwarding mode for a specific group."""
    if mode not in VALID_MODES:
        logger.error(f"Attempted to set invalid mode '{mode}' for chat_id {chat_id}")
        return False
    _group_settings[chat_id] = mode
    logger.info(f"Set mode for chat_id {chat_id} to '{mode}'")
    return True

def get_group_mode(chat_id: int) -> str:
    """Gets the forwarding mode for a specific group, defaulting to 'full'."""
    # defaultdict handles the default case automatically
    mode = _group_settings[chat_id]
    # logger.debug(f"Retrieved mode for chat_id {chat_id}: '{mode}'") # Optional: Can be noisy
    return mode

def get_current_settings() -> dict:
    """Returns a copy of the current settings dictionary."""
    # Return a copy to prevent external modification
    return dict(_group_settings)