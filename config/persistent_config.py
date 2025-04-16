# config/persistent_config.py
import asyncio
import json
import logging
import os
from typing import List, Set

from config import settings # To access PROJECT_ROOT

logger = logging.getLogger(__name__)

TARGET_GROUPS_FILE = os.path.join(settings.PROJECT_ROOT, "target_groups.json")
# Use an asyncio Lock for safe concurrent file access
_file_lock = asyncio.Lock()

# Internal cache to avoid reading file *constantly* if reads are very frequent,
# but prioritize reading from file for add/remove operations.
# For this use case (reading once per incoming message), caching might be overkill,
# but it's here as an example pattern. We'll primarily rely on direct file reads
# in the message handler for simplicity and guaranteed freshness.
# _cached_groups: Set[int] = set()
# _cache_loaded = False

async def load_target_groups() -> List[int]:
    """Loads the list of target group IDs from the JSON file."""
    async with _file_lock:
        try:
            if os.path.exists(TARGET_GROUPS_FILE):
                with open(TARGET_GROUPS_FILE, 'r', encoding='utf-8') as f:
                    group_ids = json.load(f)
                    if isinstance(group_ids, list):
                        # Ensure all elements are integers
                        valid_ids = {int(gid) for gid in group_ids if isinstance(gid, (int, str)) and str(gid).lstrip('-').isdigit()}
                        logger.debug(f"Loaded {len(valid_ids)} target groups from {TARGET_GROUPS_FILE}")
                        return list(valid_ids)
                    else:
                        logger.error(f"Invalid format in {TARGET_GROUPS_FILE}. Expected a list. Starting fresh.")
                        return []
            else:
                logger.info(f"{TARGET_GROUPS_FILE} not found. Starting with an empty target group list.")
                return []
        except (json.JSONDecodeError, ValueError) as e:
            logger.error(f"Error decoding JSON or converting IDs from {TARGET_GROUPS_FILE}: {e}. Starting fresh.")
            # Optionally back up the corrupted file here
            return []
        except Exception as e:
            logger.error(f"Failed to load target groups from {TARGET_GROUPS_FILE}: {e}", exc_info=True)
            return [] # Return empty list on failure

async def _save_target_groups(group_ids: Set[int]):
    """Saves the set of target group IDs to the JSON file (internal use)."""
    # Assumes lock is already held by caller (add/remove)
    try:
        # Convert set to list for JSON compatibility
        id_list = sorted(list(group_ids))
        with open(TARGET_GROUPS_FILE, 'w', encoding='utf-8') as f:
            json.dump(id_list, f, indent=4)
        logger.debug(f"Saved {len(id_list)} target groups to {TARGET_GROUPS_FILE}")
    except Exception as e:
        logger.error(f"Failed to save target groups to {TARGET_GROUPS_FILE}: {e}", exc_info=True)

async def add_target_group(group_id: int) -> bool:
    """Adds a group ID to the persistent list if not already present."""
    if not isinstance(group_id, int):
        logger.error(f"Attempted to add non-integer group ID: {group_id}")
        return False

    async with _file_lock:
        current_groups_list = await load_target_groups() # Load fresh inside lock
        current_groups_set = set(current_groups_list)
        if group_id not in current_groups_set:
            current_groups_set.add(group_id)
            await _save_target_groups(current_groups_set)
            logger.info(f"Added group {group_id} to persistent target list.")
            return True
        else:
            logger.debug(f"Group {group_id} is already in the target list.")
            return False

async def remove_target_group(group_id: int) -> bool:
    """Removes a group ID from the persistent list if present."""
    if not isinstance(group_id, int):
        logger.error(f"Attempted to remove non-integer group ID: {group_id}")
        return False

    async with _file_lock:
        current_groups_list = await load_target_groups() # Load fresh inside lock
        current_groups_set = set(current_groups_list)
        if group_id in current_groups_set:
            current_groups_set.remove(group_id)
            await _save_target_groups(current_groups_set)
            logger.info(f"Removed group {group_id} from persistent target list.")
            return True
        else:
            logger.debug(f"Group {group_id} was not found in the target list for removal.")
            return False