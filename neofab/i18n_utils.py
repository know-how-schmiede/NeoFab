from __future__ import annotations

import json
from pathlib import Path
from typing import Dict

DEFAULT_LANG = "en"
SUPPORTED_LANGS = ("en", "de", "fr")

I18N_DIR = Path(__file__).resolve().parent.parent / "i18n"
_translations_cache: Dict[str, dict] = {}


def load_language_file(lang: str) -> dict:
    """
    Load a language JSON file from i18n/<lang>.json.
    Returns an empty dict if missing/unreadable.
    """
    lang = (lang or DEFAULT_LANG).lower()
    file_path = I18N_DIR / f"{lang}.json"
    if not file_path.exists():
        return {}
    try:
        with file_path.open("r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, dict):
                return data
    except Exception:
        pass
    return {}


def get_translations(lang: str) -> dict:
    """
    Cached access to translations.
    """
    lang = (lang or DEFAULT_LANG).lower()
    if lang not in _translations_cache:
        _translations_cache[lang] = load_language_file(lang)
    return _translations_cache[lang]
