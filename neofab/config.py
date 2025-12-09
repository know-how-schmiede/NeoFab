import json
import logging
from datetime import timedelta
from pathlib import Path
from typing import Any, Dict, Optional

BASE_DIR = Path(__file__).resolve().parent
INSTANCE_DIR = BASE_DIR / "instance"
SETTINGS_FILE = INSTANCE_DIR / "config.json"

DEFAULT_SETTINGS = {
    "session_timeout_minutes": 30,
}

_settings_cache: Optional[Dict[str, Any]] = None
_settings_mtime: Optional[float] = None

log = logging.getLogger(__name__)


def coerce_positive_int(value: Any, fallback: int) -> int:
    try:
        value_int = int(value)
        if value_int > 0:
            return value_int
    except (TypeError, ValueError):
        pass
    return fallback


def _apply_session_timeout_setting(app, timeout_minutes: int) -> int:
    timeout_minutes = coerce_positive_int(
        timeout_minutes,
        DEFAULT_SETTINGS["session_timeout_minutes"],
    )
    app.permanent_session_lifetime = timedelta(minutes=timeout_minutes)
    return timeout_minutes


def load_app_settings(app, force_reload: bool = False) -> Dict[str, Any]:
    """
    Laedt die JSON-Konfiguration mit Fallback auf Defaults.
    Erkennt externe Aenderungen ueber mtime und laedt bei Bedarf neu.
    """
    global _settings_cache, _settings_mtime

    if not force_reload and _settings_cache is not None:
        try:
            current_mtime = SETTINGS_FILE.stat().st_mtime
        except FileNotFoundError:
            current_mtime = None
        if current_mtime == _settings_mtime:
            return _settings_cache

    settings = DEFAULT_SETTINGS.copy()
    try:
        if SETTINGS_FILE.exists():
            with SETTINGS_FILE.open("r", encoding="utf-8") as f:
                loaded = json.load(f)
            if isinstance(loaded, dict):
                settings["session_timeout_minutes"] = coerce_positive_int(
                    loaded.get("session_timeout_minutes"),
                    DEFAULT_SETTINGS["session_timeout_minutes"],
                )
            _settings_mtime = SETTINGS_FILE.stat().st_mtime
        else:
            _settings_mtime = None
    except Exception as exc:
        log.warning("Could not load settings from %s: %s", SETTINGS_FILE, exc)

    settings["session_timeout_minutes"] = _apply_session_timeout_setting(
        app,
        settings["session_timeout_minutes"],
    )
    _settings_cache = settings
    return settings


def save_app_settings(app, new_settings: Dict[str, Any]) -> Dict[str, Any]:
    """
    Schreibt Einstellungen in die JSON-Datei und aktualisiert Cache + Session-Lifetime.
    """
    global _settings_cache, _settings_mtime

    settings = DEFAULT_SETTINGS.copy()
    if isinstance(new_settings, dict):
        settings["session_timeout_minutes"] = coerce_positive_int(
            new_settings.get("session_timeout_minutes"),
            DEFAULT_SETTINGS["session_timeout_minutes"],
        )

    settings["session_timeout_minutes"] = _apply_session_timeout_setting(
        app,
        settings["session_timeout_minutes"],
    )

    try:
        SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
        with SETTINGS_FILE.open("w", encoding="utf-8") as f:
            json.dump(settings, f, ensure_ascii=False, indent=2)
        _settings_mtime = SETTINGS_FILE.stat().st_mtime
        _settings_cache = settings
    except Exception as exc:
        log.error("Could not write settings to %s: %s", SETTINGS_FILE, exc)
        raise

    return settings
