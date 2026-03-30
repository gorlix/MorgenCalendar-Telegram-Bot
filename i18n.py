import json
import logging
from pathlib import Path
from typing import Any

from database import get_user

logger = logging.getLogger(__name__)

# Cache locales
_locales = {}


def load_locales():
    """Loads English and Italian JSON strings into memory."""
    locales_dir = Path(__file__).parent / "locales"
    for lang in ["en", "it"]:
        file_path = locales_dir / f"{lang}.json"
        try:
            with open(file_path, encoding="utf-8") as f:
                _locales[lang] = json.load(f)
        except Exception as e:
            logger.error(f"Failed to load locale {lang}: {e}")
            _locales[lang] = {}


# Initial load
load_locales()


async def get_text(key: str, user_id: int, **kwargs: Any) -> str:
    """
    Fetches the localized string for a user's language setting.
    If the language is not found, defaults to English.
    """
    user_record = await get_user(user_id)
    lang = "en"
    if user_record and user_record.get("language"):
        lang = user_record["language"]

    # Fallback to English if translation is missing
    if lang not in _locales or key not in _locales[lang]:
        lang = "en"

    text = _locales.get(lang, {}).get(key, f"[{key}]")

    # Format with kwargs
    if kwargs:
        try:
            return text.format(**kwargs)
        except KeyError as e:
            logger.error(f"Missing format key {e} for i18n key '{key}'")
            return text
    return text


def get_text_sync(key: str, lang: str = "en", **kwargs: Any) -> str:
    """Synchronous getter mainly for formatters where user_id might be abstracted."""
    if lang not in _locales or key not in _locales[lang]:
        lang = "en"
    text = _locales.get(lang, {}).get(key, f"[{key}]")

    if kwargs:
        try:
            return text.format(**kwargs)
        except KeyError as e:
            logger.error(f"Missing format key {e} for i18n key '{key}'")
            return text
    return text
