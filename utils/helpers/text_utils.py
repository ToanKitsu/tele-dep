# utils/helpers/text_utils.py
import logging
import re
import html

logger = logging.getLogger(__name__)

def extract_action_and_username(text: str) -> tuple[str | None, str | None]:
    """
    Extracts the action type (Tweet, Retweet, Quote, Reply) and username,
    handling optional bold markdown around the action word and username.
    Returns (action_type, username) or (None, None).
    """
    # ... (Code của hàm extract_action_and_username giữ nguyên) ...
    if not text:
        return None, None

    # Patterns: (regex, action_name_if_matched)
    # Now explicitly look for optional ** around the action word.
    patterns = [
        # 1. Patterns with specific Action Words (allowing optional ** around action)
        # Captures ActionWord in group 1, Username in group 2
        (r"\**\s*(Retweet)\s*\**\s+from\s+\*\*([^ *]+?)\*\*", "Retweet"),
        (r"\**\s*(Tweet)\s*\**\s+from\s+\*\*([^ *]+?)\*\*", "Tweet"),
        (r"\**\s*(Quote)\s*\**\s+from\s+\*\*([^ *]+?)\*\*", "Quote"),
        (r"\**\s*(Reply)\s*\**\s+from\s+\*\*([^ *]+?)\*\*", "Reply"),

        # 2. Fallback: Just 'from **username**' - Action Unknown
        # Captures Username in group 1
        (r"from\s+\*\*([^ *]+?)\*\*", None) # Make sure this doesn't overlap greedily
    ]

    # Prioritize patterns with action words
    for pattern, action_type_name in patterns:
        if action_type_name: # Only check action word patterns first
             match = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
             if match:
                action_type = action_type_name # Use the predefined name
                username = match.group(2).strip() # Username is the second capture group
                logger.debug(f"Extracted Action/User: '{action_type}' / '{username}' (Pattern: Action Word)")
                return action_type, username

    # If no action word pattern matched, check the fallback pattern
    fallback_pattern, _ = patterns[-1] # Get the 'from **username**' pattern
    match = re.search(fallback_pattern, text, re.IGNORECASE | re.MULTILINE)
    if match:
        action_type = None # Action is unknown
        username = match.group(1).strip() # Username is the first capture group
        logger.debug(f"Extracted User only: '{username}' (Pattern: Fallback 'from')")
        return action_type, username


    # If absolutely nothing matched
    logger.warning(f"Could not extract any username/action structure from text: '{text[:70]}...'")
    return None, None

def get_action_emoji(action_type: str | None) -> str:
    """Gets the emoji corresponding to the Twitter action type."""
    # ... (Code của hàm get_action_emoji giữ nguyên) ...
    if action_type == "Retweet": return "🔄"
    elif action_type == "Quote": return "💬"
    elif action_type == "Reply": return "↩️" # Using a different reply emoji
    elif action_type == "Tweet": return "📝"
    else: return "➡️" # Fallback/Unknown action

def format_full_mode_header_html(action_type: str | None, username: str | None, original_tweet_url: str | None) -> str | None:
    """Formats the header line for Full Mode messages using HTML."""
    # ... (Code của hàm format_full_mode_header_html giữ nguyên) ...
    # Handle cases where info might be missing but we still want a header
    emoji = get_action_emoji(action_type)
    action_text = action_type if action_type else "Action" # Default text if type unknown
    safe_action_text = html.escape(action_text)

    if username:
        safe_username = html.escape(username)
        if original_tweet_url:
             safe_original_url = html.escape(original_tweet_url) # URL for the inline link
             # Format: Emoji <b>Action</b> from <a href="original_tweet_url">username</a>
             return f'{emoji} <b>{safe_action_text}</b> from <a href="{safe_original_url}">{safe_username}</a>'
        else:
             # Format: Emoji <b>Action</b> from <b>username</b> (no link)
             return f'{emoji} <b>{safe_action_text}</b> from <b>{safe_username}</b>'
    else:
        # Format: Emoji <b>Action</b> (no user)
        return f'{emoji} <b>{safe_action_text}</b>'

# Lưu ý: format_fxtwitter_message_html và format_full_message_body sẽ được chuyển qua
# handlers/message_processing/content_formatter.py vì chúng thuộc về logic định dạng nội dung gửi đi.