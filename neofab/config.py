import json
import logging
import os
import re
from datetime import timedelta
from pathlib import Path
from typing import Any, Dict, Optional

from cryptography.fernet import Fernet, InvalidToken

from status_messages import normalize_status_messages

BASE_DIR = Path(__file__).resolve().parent
INSTANCE_DIR = BASE_DIR / "instance"
SETTINGS_FILE = INSTANCE_DIR / "config.json"

EMAIL_ACTION_DEFS = (
    {
        "key": "new_order",
        "group": "orders",
    },
    {
        "key": "order_in_progress",
        "group": "orders",
    },
    {
        "key": "order_completed",
        "group": "orders",
    },
    {
        "key": "poster_printed",
        "group": "orders",
    },
    {
        "key": "announcement_attention_email",
        "group": "announcements",
    },
)
EMAIL_ACTION_KEYS = tuple(item["key"] for item in EMAIL_ACTION_DEFS)
EMAIL_ACTION_STATE_ENABLED = "enabled"
EMAIL_ACTION_STATE_DISABLED = "disabled"
DEFAULT_EMAIL_ACTION_SETTINGS = {
    key: EMAIL_ACTION_STATE_ENABLED
    for key in EMAIL_ACTION_KEYS
}

DEFAULT_SETTINGS = {
    "session_timeout_minutes": 30,
    "dashboard_rows_per_page": 25,
    "time_display_offset_hours": 0,
    "registration_domain_check_enabled": False,
    "registration_allowed_domains": "",
    "smtp_host": "",
    "smtp_port": 0,
    "smtp_use_tls": False,
    "smtp_use_ssl": False,
    "smtp_user": "",
    "smtp_password": "",
    "smtp_password_enc": "",
    "smtp_from_address": "",
    "email_actions": DEFAULT_EMAIL_ACTION_SETTINGS.copy(),
    "status_messages": {},
    "imprint_markdown": "",
    "privacy_markdown": "",
}
DASHBOARD_ROWS_PER_PAGE_OPTIONS = (10, 25, 50)

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


def coerce_dashboard_rows_per_page(value: Any, fallback: int | None = None) -> int:
    fallback_value = fallback if fallback in DASHBOARD_ROWS_PER_PAGE_OPTIONS else DEFAULT_SETTINGS["dashboard_rows_per_page"]
    value_int = coerce_positive_int(value, fallback_value)
    return value_int if value_int in DASHBOARD_ROWS_PER_PAGE_OPTIONS else fallback_value


def coerce_time_display_offset_hours(value: Any, fallback: int | None = None) -> int:
    fallback_value = fallback if isinstance(fallback, int) else DEFAULT_SETTINGS["time_display_offset_hours"]
    try:
        value_int = int(value)
    except (TypeError, ValueError):
        return fallback_value
    if -23 <= value_int <= 23:
        return value_int
    return fallback_value


def coerce_bool(value: Any, fallback: bool = False) -> bool:
    if value is None:
        return fallback
    if isinstance(value, bool):
        return value
    text_value = str(value).strip().lower()
    if text_value in {"1", "true", "yes", "on", "ja"}:
        return True
    if text_value in {"0", "false", "no", "off", "nein"}:
        return False
    return fallback


def normalize_registration_domains(value: Any) -> list[str]:
    """Normalize semicolon-separated domain input to unique lower-case entries."""
    text_value = str(value or "")
    parts = re.split(r"[;,\n\r]+", text_value)
    normalized: list[str] = []
    seen: set[str] = set()
    for part in parts:
        domain = part.strip().lower()
        # Normalize common Unicode dash variants to a plain hyphen.
        domain = re.sub(r"[‐-―−]", "-", domain)
        # If an email address was pasted accidentally, keep only its domain part.
        if "@" in domain:
            domain = domain.rsplit("@", 1)[-1]
        domain = domain.lstrip("@")
        if not domain:
            continue
        try:
            domain = domain.encode("idna").decode("ascii")
        except Exception:
            continue
        if not re.fullmatch(r"[a-z0-9.-]+", domain):
            continue
        domain = domain.strip(".")
        if not domain or domain in seen:
            continue
        seen.add(domain)
        normalized.append(domain)
    return normalized


def serialize_registration_domains(domains: list[str]) -> str:
    return "; ".join(domains)


def is_registration_domain_allowed(email_domain: str, allowed_domains: list[str]) -> bool:
    domain = str(email_domain or "").strip().lower().strip(".")
    if not domain:
        return False
    for allowed in allowed_domains:
        allowed_domain = str(allowed or "").strip().lower().strip(".")
        if not allowed_domain:
            continue
        if domain == allowed_domain or domain.endswith(f".{allowed_domain}"):
            return True
    return False


def normalize_email_actions(value: Any) -> Dict[str, str]:
    actions = DEFAULT_EMAIL_ACTION_SETTINGS.copy()
    if isinstance(value, dict):
        legacy_status_state = str(value.get("order_status_changed", "") or "").strip()
        if legacy_status_state in (EMAIL_ACTION_STATE_ENABLED, EMAIL_ACTION_STATE_DISABLED):
            actions["order_in_progress"] = legacy_status_state
            actions["order_completed"] = legacy_status_state
        for key in EMAIL_ACTION_KEYS:
            state = str(value.get(key, actions[key]) or "").strip()
            if state in (EMAIL_ACTION_STATE_ENABLED, EMAIL_ACTION_STATE_DISABLED):
                actions[key] = state
    return actions


def is_email_action_enabled(settings: Dict[str, Any], action_key: str) -> bool:
    actions = normalize_email_actions(settings.get("email_actions"))
    return actions.get(action_key) == EMAIL_ACTION_STATE_ENABLED


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
                settings["dashboard_rows_per_page"] = coerce_dashboard_rows_per_page(
                    loaded.get("dashboard_rows_per_page"),
                    DEFAULT_SETTINGS["dashboard_rows_per_page"],
                )
                settings["time_display_offset_hours"] = coerce_time_display_offset_hours(
                    loaded.get("time_display_offset_hours"),
                    DEFAULT_SETTINGS["time_display_offset_hours"],
                )
                settings["registration_domain_check_enabled"] = coerce_bool(
                    loaded.get("registration_domain_check_enabled"),
                    DEFAULT_SETTINGS["registration_domain_check_enabled"],
                )
                settings["registration_allowed_domains"] = serialize_registration_domains(
                    normalize_registration_domains(loaded.get("registration_allowed_domains", ""))
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
                settings["email_actions"] = normalize_email_actions(
                    loaded.get("email_actions", DEFAULT_SETTINGS.get("email_actions"))
                )
                settings["status_messages"] = normalize_status_messages(
                    loaded.get("status_messages", DEFAULT_SETTINGS.get("status_messages"))
                )
                settings["imprint_markdown"] = str(loaded.get("imprint_markdown", "") or "")
                settings["privacy_markdown"] = str(loaded.get("privacy_markdown", "") or "")
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
        settings["dashboard_rows_per_page"] = coerce_dashboard_rows_per_page(
            new_settings.get("dashboard_rows_per_page"),
            DEFAULT_SETTINGS["dashboard_rows_per_page"],
        )
        settings["time_display_offset_hours"] = coerce_time_display_offset_hours(
            new_settings.get("time_display_offset_hours"),
            DEFAULT_SETTINGS["time_display_offset_hours"],
        )
        settings["registration_domain_check_enabled"] = coerce_bool(
            new_settings.get("registration_domain_check_enabled"),
            DEFAULT_SETTINGS["registration_domain_check_enabled"],
        )
        settings["registration_allowed_domains"] = serialize_registration_domains(
            normalize_registration_domains(new_settings.get("registration_allowed_domains", ""))
        )
        settings["smtp_host"] = str(new_settings.get("smtp_host", "") or "").strip()
        settings["smtp_port"] = coerce_positive_int(new_settings.get("smtp_port"), 0)
        settings["smtp_use_tls"] = bool(new_settings.get("smtp_use_tls"))
        settings["smtp_use_ssl"] = bool(new_settings.get("smtp_use_ssl"))
        settings["smtp_user"] = str(new_settings.get("smtp_user", "") or "").strip()
        settings["smtp_password"] = str(new_settings.get("smtp_password", "") or "")
        settings["smtp_from_address"] = str(new_settings.get("smtp_from_address", "") or "").strip()
        settings["email_actions"] = normalize_email_actions(
            new_settings.get("email_actions", DEFAULT_SETTINGS.get("email_actions"))
        )
        settings["status_messages"] = normalize_status_messages(
            new_settings.get("status_messages", DEFAULT_SETTINGS.get("status_messages"))
        )
        settings["imprint_markdown"] = str(new_settings.get("imprint_markdown", "") or "")
        settings["privacy_markdown"] = str(new_settings.get("privacy_markdown", "") or "")

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
