import json
import logging
import os
from datetime import timedelta
from pathlib import Path
from typing import Any, Dict, Optional

from cryptography.fernet import Fernet, InvalidToken

BASE_DIR = Path(__file__).resolve().parent
INSTANCE_DIR = BASE_DIR / "instance"
SETTINGS_FILE = INSTANCE_DIR / "config.json"

DEFAULT_SETTINGS = {
    "session_timeout_minutes": 30,
    "smtp_host": "",
    "smtp_port": 0,
    "smtp_use_tls": False,
    "smtp_use_ssl": False,
    "smtp_user": "",
    "smtp_password": "",
    "smtp_password_enc": "",
    "smtp_from_address": "",
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


def _get_fernet() -> Optional[Fernet]:
    key = os.environ.get("NEOFAB_CONFIG_KEY")
    if not key:
        return None
    try:
        return Fernet(key.encode("utf-8"))
    except Exception as exc:
        log.warning("Invalid NEOFAB_CONFIG_KEY, falling back to plain text: %s", exc)
        return None


def _decrypt_secret(token: str) -> str:
    """
    Attempts to decrypt a Fernet token. Returns an empty string on failure.
    """
    fernet = _get_fernet()
    if not fernet or not token:
        return ""
    try:
        return fernet.decrypt(token.encode("ascii")).decode("utf-8")
    except InvalidToken:
        log.warning("Could not decrypt smtp_password_enc: invalid token")
    except Exception as exc:
        log.warning("Could not decrypt smtp_password_enc: %s", exc)
    return ""


def _encrypt_secret(value: str) -> tuple[str, bool]:
    """
    Encrypts a value using Fernet if a key is configured.
    Returns (token, True) when encryption is used, otherwise (value, False).
    """
    if not value:
        return "", False
    fernet = _get_fernet()
    if not fernet:
        log.info("NEOFAB_CONFIG_KEY not set, storing smtp_password unencrypted.")
        return value, False
    try:
        token = fernet.encrypt(value.encode("utf-8")).decode("ascii")
        return token, True
    except Exception as exc:
        log.warning("Could not encrypt smtp_password, storing unencrypted: %s", exc)
        return value, False


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
                settings["smtp_host"] = str(loaded.get("smtp_host", "") or "").strip()
                settings["smtp_port"] = coerce_positive_int(loaded.get("smtp_port"), 0)
                settings["smtp_use_tls"] = bool(loaded.get("smtp_use_tls"))
                settings["smtp_use_ssl"] = bool(loaded.get("smtp_use_ssl"))
                settings["smtp_user"] = str(loaded.get("smtp_user", "") or "").strip()
                settings["smtp_password_enc"] = str(loaded.get("smtp_password_enc", "") or "")
                decrypted_pw = _decrypt_secret(settings["smtp_password_enc"])
                settings["smtp_password"] = (
                    decrypted_pw
                    if decrypted_pw
                    else str(loaded.get("smtp_password", "") or "")
                )
                settings["smtp_from_address"] = str(loaded.get("smtp_from_address", "") or "").strip()
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
        settings["smtp_host"] = str(new_settings.get("smtp_host", "") or "").strip()
        settings["smtp_port"] = coerce_positive_int(new_settings.get("smtp_port"), 0)
        settings["smtp_use_tls"] = bool(new_settings.get("smtp_use_tls"))
        settings["smtp_use_ssl"] = bool(new_settings.get("smtp_use_ssl"))
        settings["smtp_user"] = str(new_settings.get("smtp_user", "") or "").strip()
        settings["smtp_password"] = str(new_settings.get("smtp_password", "") or "")
        settings["smtp_from_address"] = str(new_settings.get("smtp_from_address", "") or "").strip()

    settings["session_timeout_minutes"] = _apply_session_timeout_setting(
        app,
        settings["session_timeout_minutes"],
    )

    persist_settings = settings.copy()
    encrypted_pw, used_encryption = _encrypt_secret(settings.get("smtp_password", ""))
    if used_encryption:
        persist_settings["smtp_password_enc"] = encrypted_pw
        persist_settings["smtp_password"] = ""
    else:
        persist_settings["smtp_password_enc"] = ""

    try:
        SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
        with SETTINGS_FILE.open("w", encoding="utf-8") as f:
            json.dump(persist_settings, f, ensure_ascii=False, indent=2)
        _settings_mtime = SETTINGS_FILE.stat().st_mtime
        _settings_cache = settings
    except Exception as exc:
        log.error("Could not write settings to %s: %s", SETTINGS_FILE, exc)
        raise

    return settings
