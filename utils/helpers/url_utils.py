# utils/helpers/url_utils.py
import logging
from urllib.parse import urlparse, urlunparse

logger = logging.getLogger(__name__)

def create_fxtwitter_url(original_url: str | None) -> str | None:
    """Converts a twitter.com or x.com URL to an fxtwitter.com URL."""
    # ... (Code của hàm create_fxtwitter_url giữ nguyên) ...
    if not original_url:
        return None
    try:
        parsed = urlparse(original_url)
        # Check if it's a twitter or x.com URL
        netloc_lower = parsed.netloc.lower()
        if netloc_lower == 'twitter.com' or netloc_lower == 'x.com' or netloc_lower.endswith('.twitter.com') or netloc_lower.endswith('.x.com'):
            # Reconstruct the URL with fxtwitter.com as the netloc
            fxtwitter_parsed = parsed._replace(netloc='fxtwitter.com')
            # Ensure scheme is present, default to https if missing
            if not fxtwitter_parsed.scheme:
                fxtwitter_parsed = fxtwitter_parsed._replace(scheme='https')
            return urlunparse(fxtwitter_parsed)
        else:
            logger.debug(f"URL '{original_url}' is not a Twitter/X URL, cannot convert.")
            return original_url # Return original if not twitter/x
    except Exception as e:
        logger.error(f"Error parsing or converting URL '{original_url}': {e}")
        return None # Return None on error