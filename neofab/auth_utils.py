from datetime import datetime, timedelta
from functools import wraps
from typing import Callable

from flask import session, redirect, url_for, flash, request
from flask_login import current_user, login_required, logout_user
from werkzeug.exceptions import abort

from config import DEFAULT_SETTINGS, coerce_positive_int, load_app_settings

SESSION_LAST_ACTIVE_KEY = "last_active_utc"


def roles_required(*roles):
    """
    Decorator: erlaubt Zugriff nur, wenn current_user.role in roles ist.
    Nutzung:
        @roles_required("admin")
        @roles_required("admin", "manager")
    """

    def decorator(view_func):
        @wraps(view_func)
        @login_required
        def wrapped(*args, **kwargs):
            if current_user.role not in roles:
                abort(403)
            return view_func(*args, **kwargs)

        return wrapped

    return decorator


def register_session_timeout(app, get_translator: Callable[[], Callable[[str], str] | None]):
    """
    Registriert einen before_request-Handler, der Inaktivitaetstimeout durchsetzt.
    """

    @app.before_request
    def enforce_session_timeout():
        if not current_user.is_authenticated:
            return

        settings = load_app_settings(app)
        timeout_minutes = coerce_positive_int(
            settings.get("session_timeout_minutes"),
            DEFAULT_SETTINGS["session_timeout_minutes"],
        )

        now = datetime.utcnow()
        last_seen_raw = session.get(SESSION_LAST_ACTIVE_KEY)

        if last_seen_raw:
            try:
                last_seen = datetime.fromisoformat(last_seen_raw)
            except Exception:
                last_seen = None

            if last_seen and now - last_seen > timedelta(minutes=timeout_minutes):
                logout_user()
                session.clear()
                trans = get_translator() or (lambda key: key)
                flash(trans("flash_session_expired"), "warning")
                return redirect(url_for("login"))

        is_static_request = (request.endpoint or "").startswith("static")
        if not is_static_request:
            session.permanent = True
            session[SESSION_LAST_ACTIVE_KEY] = now.isoformat()
