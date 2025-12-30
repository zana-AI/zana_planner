"""
Translation module using Google Cloud Translation API.
Provides caching to minimize API calls for frequently used messages.
"""

from typing import Dict

from llms.llm_env_utils import load_llm_env
from utils.logger import get_logger

logger = get_logger(__name__)

# Translation cache to avoid repeated API calls
_translation_cache: Dict[str, str] = {}

# Load GCP configuration
cfg = load_llm_env()
project_id = cfg.get("GCP_PROJECT_ID")
location = cfg.get("GCP_LOCATION", "us-central1")


def translate_text(text: str, target_lang: str, source_lang: str = "en") -> str:
    """
    Translate text using Google Cloud Translation API with caching.
    
    Args:
        text: Text to translate
        target_lang: Target language code (e.g., "fa", "fr")
        source_lang: Source language code (default: "en")
    
    Returns:
        Translated text or original text if translation fails
    """
    if not text or target_lang == source_lang:
        return text
    
    # Create cache key
    cache_key = f"{source_lang}:{target_lang}:{text}"
    
    # Check cache first
    if cache_key in _translation_cache:
        return _translation_cache[cache_key]
    
    try:
        # Import GCP translate client
        from google.cloud import translate_v3 as translate
        
        client = translate.TranslationServiceClient()
        parent = f"projects/{project_id}/locations/{location}"
        
        request = translate.TranslateTextRequest(
            contents=[text],
            target_language_code=target_lang,
            source_language_code=source_lang or "",
            parent=parent,
            mime_type="text/plain"
        )
        
        response = client.translate_text(request=request)
        translated_text = response.translations[0].translated_text
        
        # Cache the result
        _translation_cache[cache_key] = translated_text
        
        logger.debug(f"Translated '{text[:50]}...' from {source_lang} to {target_lang}")
        return translated_text
        
    except ImportError:
        logger.error("google-cloud-translate not available. Install with: pip install google-cloud-translate")
        return text
    except Exception as e:
        logger.error(f"Translation failed for '{text[:50]}...': {str(e)}")
        return text


def clear_translation_cache() -> None:
    """Clear the translation cache."""
    global _translation_cache
    _translation_cache.clear()
    logger.info("Translation cache cleared")


def get_cache_size() -> int:
    """Get the current size of the translation cache."""
    return len(_translation_cache)
