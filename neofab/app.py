# ============================================================
# NeoFab ÔÇô einfache 3D-Druck-Auftragsverwaltung
# ============================================================
# - User-Registrierung & Login
# - Auftr├ñge mit Material / Farbe
# - Chat-├ñhnliche Kommunikation pro Auftrag
# - Upload mehrerer 3D-Dateien (STL / 3MF) pro Auftrag
# - Download & L├Âschen von Dateien
# - Dashboard mit Files-Z├ñhler pro Auftrag
# ============================================================

from version import APP_VERSION
from datetime import datetime, timedelta
from email.utils import getaddresses
from pathlib import Path
import base64
import binascii
import hashlib
import mimetypes
import os
import logging
import re
import math
import struct
import secrets
from time import perf_counter
from urllib.parse import parse_qs, urlparse

from sqlalchemy import func, or_, text

from markupsafe import Markup, escape
from werkzeug.exceptions import RequestEntityTooLarge

from flask import (
    Flask,
    render_template,
    redirect,
    url_for,
    request,
    flash,
    session,
    jsonify,
    send_from_directory,
    abort,
)

from flask_login import (
    LoginManager,
    login_user,
    login_required,
    logout_user,
    current_user,
)

from werkzeug.utils import secure_filename

from typing import List, Tuple, Optional
from io import BytesIO

from PIL import Image, ImageDraw

from jinja2 import Environment, FileSystemLoader, select_autoescape, Template
from config import (
    DASHBOARD_COLUMN_DEFS,
    DASHBOARD_ROWS_PER_PAGE_OPTIONS,
    DEFAULT_SETTINGS,
    SETTINGS_FILE,
    is_registration_domain_allowed,
    coerce_positive_int,
    load_app_settings,
    normalize_dashboard_columns,
    normalize_registration_domains,
    save_app_settings,
)
from i18n_utils import DEFAULT_LANG, SUPPORTED_LANGS, get_translations
from legal_markdown import render_legal_markdown
from notifications import (
    send_announcement_attention_notification,
    send_admin_order_notification,
    send_order_status_change_notification,
    send_password_reset_notification,
    send_poster_printed_notification,
    send_procurement_article_list_email,
    send_user_activation_notification,
    send_user_welcome_notification,
)
from schema_utils import ensure_order_id_sequence_table, ensure_training_playlist_schema, reserve_next_order_id
from status_messages import (
    ORDER_STATUS_DEFS,
    PRINT_JOB_STATUS_DEFS,
    build_status_context,
)
from time_utils import (
    format_app_datetime,
    get_app_timezone_name,
    parse_app_datetime_input,
    to_app_datetime,
)
from auth_utils import (
    roles_required,
    register_session_timeout,
    SESSION_LAST_ACTIVE_KEY,
)
from audit_logs import maybe_cleanup_expired_logs, write_audit_log
from routes import create_admin_blueprint
from models import (
    db,
    User,
    UserActivationToken,
    UserPasswordResetToken,
    Order,
    OrderCategory,
    OrderArea,
    OrderWorkJob,
    UserOrderCategoryPermission,
    UserOrderAreaPreference,
    UserEmailFavorite,
    OrderPosterFile,
    OrderProcurementArticle,
    OrderMessage,
    OrderReadStatus,
    Announcement,
    AnnouncementRead,
    OrderFile,
    OrderPrintJob,
    OrderImage,
    OrderVideo,
    OrderTag,
    Material,
    Color,
    CostCenter,
    PrinterProfile,
    FilamentMaterial,
    TrainingPlaylist,
    TrainingVideo,
)

ANNOUNCEMENT_FORM_TOKEN_KEY = "announcement_form_token"

REGISTRATION_LANGUAGE_OPTIONS = [
    ("de", "Deutsch"),
    ("en", "English"),
    ("fr", "Francais"),
]

REGISTRATION_SALUTATION_OPTIONS = {
    "de": ["Frau", "Herr"],
    "en": ["Ms.", "Mr.", "Mx."],
    "fr": ["Madame", "Monsieur", "Mx"],
}


def _new_announcement_form_token() -> str:
    form_token = secrets.token_urlsafe(24)
    session[ANNOUNCEMENT_FORM_TOKEN_KEY] = form_token
    return form_token


def _consume_announcement_form_token() -> bool:
    form_token = (request.form.get("form_token") or "").strip()
    expected_token = session.pop(ANNOUNCEMENT_FORM_TOKEN_KEY, None)
    return bool(form_token and expected_token and form_token == expected_token)


def _reject_duplicate_announcement_submission(next_url: str | None = None):
    trans = inject_globals().get("t")
    write_audit_log(
        app,
        "announcement_duplicate_ignored",
        details={"path": request.path},
        user=current_user,
    )
    flash(trans("flash_duplicate_submission_ignored"), "warning")
    return redirect(next_url or request.form.get("next") or url_for("dashboard"))

XHTML2PDF_IMPORT_ERR = None
pisa = None
XHTML2PDF_AVAILABLE = False
try:
    from xhtml2pdf import pisa as _pisa  # type: ignore
    pisa = _pisa
    XHTML2PDF_AVAILABLE = True
except Exception as exc:
    XHTML2PDF_IMPORT_ERR = exc
    # Versuch: Usersite dem Pfad hinzuf├╝gen (falls Paket per --user installiert ist)
    try:
        import site, sys  # noqa
        user_site = site.getusersitepackages()
        if isinstance(user_site, str) and user_site not in sys.path:
            sys.path.append(user_site)
        from xhtml2pdf import pisa as _pisa  # type: ignore
        pisa = _pisa
        XHTML2PDF_AVAILABLE = True
        XHTML2PDF_IMPORT_ERR = None
    except Exception as exc2:
        XHTML2PDF_IMPORT_ERR = exc2


# ============================================================
# Grundkonfiguration & Logging
# ============================================================

app = Flask(__name__)

# Basis-Verzeichnis (Root des Projekts)
BASE_DIR = Path(__file__).resolve().parent

# Upload-Ordner f├╝r 3D-Modelle, z.B. "uploads/models"
UPLOAD_FOLDER = BASE_DIR / "uploads" / "models"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config["UPLOAD_FOLDER"] = str(UPLOAD_FOLDER)

# Upload-Ordner f├╝r Projektbilder
IMAGE_UPLOAD_FOLDER = BASE_DIR / "uploads" / "images"
os.makedirs(IMAGE_UPLOAD_FOLDER, exist_ok=True)
app.config["IMAGE_UPLOAD_FOLDER"] = str(IMAGE_UPLOAD_FOLDER)

VIDEO_UPLOAD_FOLDER = BASE_DIR / "uploads" / "videos"
os.makedirs(VIDEO_UPLOAD_FOLDER, exist_ok=True)
app.config["VIDEO_UPLOAD_FOLDER"] = str(VIDEO_UPLOAD_FOLDER)

GCODE_UPLOAD_FOLDER = BASE_DIR / "uploads" / "gcode"
os.makedirs(GCODE_UPLOAD_FOLDER, exist_ok=True)
app.config["GCODE_UPLOAD_FOLDER"] = str(GCODE_UPLOAD_FOLDER)

POSTER_UPLOAD_FOLDER = BASE_DIR / "uploads" / "posters"
os.makedirs(POSTER_UPLOAD_FOLDER, exist_ok=True)
app.config["POSTER_UPLOAD_FOLDER"] = str(POSTER_UPLOAD_FOLDER)
PROCUREMENT_NOTE_UPLOAD_FOLDER = BASE_DIR / "uploads" / "procurement_notes"
os.makedirs(PROCUREMENT_NOTE_UPLOAD_FOLDER, exist_ok=True)
app.config["PROCUREMENT_NOTE_UPLOAD_FOLDER"] = str(PROCUREMENT_NOTE_UPLOAD_FOLDER)

TRAINING_UPLOAD_FOLDER = BASE_DIR / "uploads" / "tutorials"
os.makedirs(TRAINING_UPLOAD_FOLDER, exist_ok=True)
app.config["TRAINING_UPLOAD_FOLDER"] = str(TRAINING_UPLOAD_FOLDER)

# Max width for generated thumbnails (px)
THUMBNAIL_MAX_WIDTH = 200

# Thumbnail sizes for 3D model previews
MODEL_THUMB_SMALL_SIZE = (240, 240)
MODEL_THUMB_LARGE_SIZE = (1024, 768)
MODEL_THUMB_PADDING = 12
MODEL_THUMB_ZOOM = 2.0
MODEL_THUMB_MAX_TRIANGLES = 12000
MODEL_THUMB_SMALL_TRIANGLES = 3000
MODEL_THUMB_LARGE_TRIANGLES = 8000


# Optionaler PDF-Template-Pfad (HTML)
PDF_TEMPLATE_PATH = os.environ.get(
    "NEOFAB_PDF_TEMPLATE",
    str(BASE_DIR.parent / "doku" / "pdf_template.html"),
)


# Maximal erlaubte Upload-Groesse
MAX_UPLOAD_SIZE_MB = 200
app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD_SIZE_MB * 1024 * 1024

# Einfache Logging-Konfiguration. Debug kann bei Bedarf ueber NEOFAB_LOG_LEVEL=DEBUG
# aktiviert werden, ist fuer den systemd/Gunicorn-Betrieb aber zu laut.
LOG_LEVEL_NAME = os.environ.get("NEOFAB_LOG_LEVEL", "INFO").strip().upper()
LOG_LEVEL = getattr(logging, LOG_LEVEL_NAME, logging.INFO)
logging.basicConfig(level=LOG_LEVEL)
app.logger.setLevel(LOG_LEVEL)

# Auftrags-Status-Codes (interne Werte + Labels)
ORDER_STATUSES = [(item["key"], item["label"]) for item in ORDER_STATUS_DEFS]
ORDER_STATUS_VALUES = [item["key"] for item in ORDER_STATUS_DEFS]

# Mapping der Status-Codes zu lesbaren Labels

# Abw├ñrtskompatibilit├ñt f├╝r alte deutsche Statuswerte

PRINT_JOB_STATUSES = [(item["key"], item["label"]) for item in PRINT_JOB_STATUS_DEFS]
PRINT_JOB_STATUS_VALUES = [item["key"] for item in PRINT_JOB_STATUS_DEFS]

DEFAULT_ORDER_CATEGORIES = [
    {
        "key": "3d_print",
        "name": "3D-Druck",
        "description": "Additive Fertigung mit 3D-Druckern und G-Code-Druckauftraegen.",
        "enabled_tabs": "general,project,files,print-jobs,communication",
        "allowed_worker_roles": "admin",
    },
    {
        "key": "plotter",
        "name": "Plotter",
        "description": "Plotter- und Schneidauftraege.",
        "enabled_tabs": "general,posters,communication",
        "allowed_worker_roles": "admin",
    },
    {
        "key": "cnc",
        "name": "CNC-Fraesen",
        "description": "Subtraktive Fertigung mit CNC-Fraesen.",
        "enabled_tabs": "general,files,communication",
        "allowed_worker_roles": "admin",
    },
    {
        "key": "procurement",
        "name": "Beschaffung",
        "description": "Beschaffung von Artikeln und Materialien inkl. Lieferanteninformationen.",
        "enabled_tabs": "general,articles,communication",
        "allowed_worker_roles": "admin",
    },
]

ANNOUNCEMENT_PRIORITY_META = {
    "info": {"label": "announcement_priority_info", "icon": "bi-info-circle", "class": "text-primary"},
    "notice": {"label": "announcement_priority_notice", "icon": "bi-exclamation-circle", "class": "text-info"},
    "important": {"label": "announcement_priority_important", "icon": "bi-exclamation-triangle", "class": "text-warning"},
    "warning": {"label": "announcement_priority_warning", "icon": "bi-exclamation-octagon", "class": "text-danger"},
    "attention_email": {"label": "announcement_priority_attention_email", "icon": "bi-envelope-exclamation", "class": "text-danger fw-semibold"},
}

# Secret Key & Datenbank-Config
app.config["SECRET_KEY"] = os.environ.get("NEOFAB_SECRET_KEY", "dev-secret-change-me")

# SQLite-DB im Projektverzeichnis (absoluter Pfad)
db_path = BASE_DIR / "neofab.db"
app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{db_path}"

app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

load_app_settings(app)


def to_local_datetime(value: datetime | None) -> datetime | None:
    try:
        settings = load_app_settings(app)
    except Exception:
        settings = None
    return to_app_datetime(value, settings)


def format_local_datetime(value: datetime | None, fmt: str = "%Y-%m-%d %H:%M") -> str:
    try:
        settings = load_app_settings(app)
    except Exception:
        settings = None
    return format_app_datetime(value, settings, fmt)


def get_status_context(translator=None) -> dict:
    settings = load_app_settings(app)
    return build_status_context(settings, translator)


# ============================================================
# Globale Template-Variablen
# ============================================================

@app.context_processor
def inject_globals():
    """
    Stellt globale Werte in allen Templates zur Verf├╝gung.
    """
    def current_language():
        lang = DEFAULT_LANG
        if current_user.is_authenticated and getattr(current_user, "language", None):
            lang = (current_user.language or DEFAULT_LANG).lower()

        for code in SUPPORTED_LANGS:
            if lang.startswith(code):
                return code
        return DEFAULT_LANG

    def t(key):
        lang = current_language()
        lang_trans = get_translations(lang)
        default_trans = get_translations(DEFAULT_LANG)
        return lang_trans.get(key, default_trans.get(key, key))

    def current_theme_mode():
        mode = "light"
        if current_user.is_authenticated and getattr(current_user, "theme_mode", None):
            mode = (current_user.theme_mode or "light").strip().lower()
        return "dark" if mode == "dark" else "light"

    status_context = get_status_context(t)
    settings = load_app_settings(app)
    theme_mode = current_theme_mode()
    # Keep one Bootswatch base theme for both modes; dark mode is handled via CSS variables.
    theme_bootswatch_slug = "lux"
    return {
        "app_version": APP_VERSION,
        "max_upload_size_mb": MAX_UPLOAD_SIZE_MB,
        "max_upload_size_bytes": app.config["MAX_CONTENT_LENGTH"],
        "status_labels": status_context["order_status_labels"],
        "status_styles": status_context["order_status_styles"],
        "print_job_status_labels": status_context["print_job_status_labels"],
        "print_job_status_styles": status_context["print_job_status_styles"],
        "order_statuses": status_context["order_statuses"],
        "print_job_statuses": status_context["print_job_statuses"],
        "current_language": current_language,
        "current_theme_mode": current_theme_mode,
        "theme_bootswatch_slug": theme_bootswatch_slug,
        "t": t,
        "fmt_datetime": format_local_datetime,
        "app_timezone_name": get_app_timezone_name(),
        "time_display_offset_hours": int(settings.get("time_display_offset_hours", 0) or 0),
        "render_markdown": render_legal_markdown,
    }


@app.errorhandler(RequestEntityTooLarge)
def handle_request_entity_too_large(_error):
    trans = inject_globals().get("t")
    flash(trans("flash_upload_too_large"), "danger")

    if request.endpoint == "order_detail" and request.view_args and request.view_args.get("order_id"):
        tab = request.args.get("tab")
        if tab not in {"files", "print-jobs", "posters", "articles"}:
            tab = "files"
        return redirect(url_for("order_detail", order_id=request.view_args["order_id"], tab=tab), code=303)

    return redirect(request.referrer or url_for("dashboard"), code=303)


def get_order_category(order: Order) -> OrderCategory | None:
    category = getattr(order, "category", None)
    if category:
        return category
    return OrderCategory.query.filter_by(key="3d_print").first()


def is_3d_print_order(order: Order) -> bool:
    category = get_order_category(order)
    return bool(category and category.key == "3d_print")


def is_plotter_order(order: Order) -> bool:
    category = get_order_category(order)
    return bool(category and category.key == "plotter")


def is_procurement_order(order: Order) -> bool:
    category = get_order_category(order)
    return bool(category and category.key == "procurement")


def sync_plotter_order_status_from_posters(order: Order) -> bool:
    """
    Synchronisiert den Auftragsstatus eines Plotter-Auftrags anhand der Plakatstatus.

    Regeln:
    - Alle Plakate "printed"  -> Auftrag "completed"
    - Mind. ein "printed"     -> Auftrag "in_progress"
    - Sonst (Plakate vorhanden) -> Auftrag "new"
    - Keine Plakate            -> keine Aenderung
    """
    if not is_plotter_order(order):
        return False
    if order.status == "cancelled":
        return False

    posters = OrderPosterFile.query.filter_by(order_id=order.id).all()
    if not posters:
        return False

    statuses = [((poster.status or "open").strip().lower()) for poster in posters]
    has_printed = any(status == "printed" for status in statuses)
    all_printed = all(status == "printed" for status in statuses)

    if all_printed:
        target_status = "completed"
    elif has_printed:
        target_status = "in_progress"
    else:
        target_status = "new"

    if order.status != target_status:
        order.status = target_status
        return True
    return False


def sync_3d_order_status_from_print_jobs(order: Order) -> bool:
    """
    Synchronisiert den Auftragsstatus eines 3D-Druckauftrags anhand der Druckauftrags-Status.

    Regeln:
    - Alle Druckauftraege "finished" -> Auftrag "completed"
    - Sonst (bei vorhandenen Druckauftraegen) mindestens "in_progress"
    - Keine Druckauftraege -> keine Aenderung
    """
    if not is_3d_print_order(order):
        return False
    if order.status == "cancelled":
        return False

    jobs = OrderPrintJob.query.filter_by(order_id=order.id).all()
    if not jobs:
        return False

    statuses = [((job.status or "upload").strip().lower()) for job in jobs]
    all_finished = all(status == "finished" for status in statuses)

    if all_finished:
        target_status = "completed"
    elif order.status == "completed":
        target_status = "in_progress"
    elif order.status in ("new", "neu"):
        target_status = "in_progress"
    else:
        target_status = order.status

    if order.status != target_status:
        order.status = target_status
        return True
    return False


def _send_relevant_order_status_email(app, order: Order, previous_status: str, status_labels: dict[str, str]) -> None:
    if previous_status == order.status:
        return
    if order.status not in {"in_progress", "completed"}:
        return
    send_order_status_change_notification(
        app,
        order,
        previous_status,
        order.status,
        status_labels,
        action_key=f"order_{order.status}",
    )


def sync_procurement_order_status_from_articles(order: Order) -> bool:
    """
    Synchronisiert den Auftragsstatus eines Beschaffungsauftrags anhand der Artikelstatus.

    Regeln:
    - Alle Artikel "delivered" -> Auftrag "completed"
    - Mindestens ein Artikel "ordered" oder "delivered" -> Auftrag "in_progress"
    - Sonst (Artikel vorhanden) -> Auftrag "new"
    - Keine Artikel -> keine Aenderung
    """
    if not is_procurement_order(order):
        return False
    if order.status == "cancelled":
        return False

    articles = OrderProcurementArticle.query.filter_by(order_id=order.id).all()
    if not articles:
        return False

    ordered_like = {"ordered", "delivered"}
    statuses = [((article.status or "open").strip().lower()) for article in articles]
    has_ordered = any(status in ordered_like for status in statuses)
    all_delivered = all(status == "delivered" for status in statuses)

    if all_delivered:
        target_status = "completed"
    elif has_ordered:
        target_status = "in_progress"
    else:
        target_status = "new"

    if order.status != target_status:
        order.status = target_status
        return True
    return False


def _procurement_articles_for_order(order: Order) -> list[OrderProcurementArticle]:
    return (
        OrderProcurementArticle.query
        .filter_by(order_id=order.id)
        .order_by(OrderProcurementArticle.position_number.asc(), OrderProcurementArticle.created_at.asc(), OrderProcurementArticle.id.asc())
        .all()
    )


def ensure_procurement_article_position_numbers(order_id: int) -> bool:
    articles = (
        OrderProcurementArticle.query
        .filter_by(order_id=order_id)
        .order_by(OrderProcurementArticle.created_at.asc(), OrderProcurementArticle.id.asc())
        .all()
    )
    next_position = max(
        (article.position_number or 0 for article in articles),
        default=0,
    ) + 1
    changed = False
    for article in articles:
        if article.position_number:
            continue
        article.position_number = next_position
        next_position += 1
        changed = True
    if changed:
        db.session.flush()
    return changed


def _all_procurement_articles_ordered(order: Order) -> bool:
    articles = _procurement_articles_for_order(order)
    if not articles:
        return False
    ordered_like = {"ordered", "delivered"}
    return all(((article.status or "open").strip().lower()) in ordered_like for article in articles)


def _send_procurement_all_ordered_status_email(
    app,
    order: Order,
    previous_status: str,
    status_labels: dict[str, str],
) -> None:
    action_key = f"order_{order.status}" if order.status in {"in_progress", "completed"} else "order_in_progress"
    send_order_status_change_notification(
        app,
        order,
        previous_status,
        order.status,
        status_labels,
        action_key=action_key,
        procurement_articles=_procurement_articles_for_order(order),
        procurement_all_ordered=True,
    )


def can_manage_order_category(order: Order, user: User) -> bool:
    if getattr(user, "role", None) == "admin":
        return True

    category = get_order_category(order)
    if not category:
        return False

    permission = UserOrderCategoryPermission.query.filter_by(
        user_id=user.id,
        category_id=category.id,
        can_manage=True,
    ).first()
    if permission:
        return True

    return user.role in category.worker_roles()


def can_view_order(order: Order, user: User) -> bool:
    return getattr(user, "role", None) == "admin" or order.user_id == user.id or can_manage_order_category(order, user)


def get_visible_order_tabs(order: Order, user: User) -> list[str]:
    category = get_order_category(order)
    tabs = category.tab_keys() if category else ["general", "files", "communication"]
    if not is_3d_print_order(order):
        tabs = [tab for tab in tabs if tab != "print-jobs"]
    if is_plotter_order(order):
        tabs = ["posters" if tab == "files" else tab for tab in tabs]
    elif "posters" in tabs:
        tabs = [tab for tab in tabs if tab != "posters"]
    if is_procurement_order(order):
        tabs = ["articles" if tab == "files" else tab for tab in tabs]
    elif "articles" in tabs:
        tabs = [tab for tab in tabs if tab != "articles"]
    if "general" not in tabs:
        tabs.insert(0, "general")
    return tabs


# ============================================================
# Session-/Auth-Handler
# ============================================================

register_session_timeout(app, lambda: inject_globals().get('t'))

# DB-Initialisierung & Hilfsfunktionen
# ============================================================

db.init_app(app)


def ensure_order_file_columns():
    """
    F├╝gt fehlende Spalten f├╝r OrderFile hinzu (leichtgewichtige Migration).
    """
    try:
        exists = db.session.execute(
            text("SELECT name FROM sqlite_master WHERE type='table' AND name='order_files'")
        ).scalar()
        if not exists:
            return

        cols = {
            row[1]
            for row in db.session.execute(text("PRAGMA table_info(order_files)"))
        }
        statements = []
        should_migrate_order_file_defaults = "material_id" not in cols
        if "note" not in cols:
            statements.append("ALTER TABLE order_files ADD COLUMN note VARCHAR(255)")
        if "quantity" not in cols:
            statements.append("ALTER TABLE order_files ADD COLUMN quantity INTEGER NOT NULL DEFAULT 1")
        if "material_id" not in cols:
            statements.append("ALTER TABLE order_files ADD COLUMN material_id INTEGER")
        if "color_id" not in cols:
            statements.append("ALTER TABLE order_files ADD COLUMN color_id INTEGER")
        if "thumb_sm_path" not in cols:
            statements.append("ALTER TABLE order_files ADD COLUMN thumb_sm_path VARCHAR(255)")
        if "thumb_lg_path" not in cols:
            statements.append("ALTER TABLE order_files ADD COLUMN thumb_lg_path VARCHAR(255)")
        if "has_3d_preview" not in cols:
            statements.append("ALTER TABLE order_files ADD COLUMN has_3d_preview BOOLEAN NOT NULL DEFAULT 0")
        if "preview_status" not in cols:
            statements.append("ALTER TABLE order_files ADD COLUMN preview_status VARCHAR(50)")

        for stmt in statements:
            db.session.execute(text(stmt))
        if statements:
            db.session.commit()
        if should_migrate_order_file_defaults:
            order_cols = {
                row[1]
                for row in db.session.execute(text("PRAGMA table_info(orders)"))
            }
            if "material_id" in order_cols:
                db.session.execute(text("""
                    UPDATE order_files
                    SET material_id = (
                        SELECT orders.material_id
                        FROM orders
                        WHERE orders.id = order_files.order_id
                    )
                    WHERE material_id IS NULL
                """))
            if "color_id" in order_cols:
                db.session.execute(text("""
                    UPDATE order_files
                    SET color_id = (
                        SELECT orders.color_id
                        FROM orders
                        WHERE orders.id = order_files.order_id
                    )
                    WHERE color_id IS NULL
                """))
            if "material_id" in order_cols or "color_id" in order_cols:
                db.session.commit()
    except Exception:
        app.logger.exception("Failed to ensure order_files columns exist")


def ensure_order_image_columns():
    """
    Adds missing columns for OrderImage (lightweight migration).
    """
    try:
        exists = db.session.execute(
            text("SELECT name FROM sqlite_master WHERE type='table' AND name='order_images'")
        ).scalar()
        if not exists:
            return

        cols = {
            row[1]
            for row in db.session.execute(text("PRAGMA table_info(order_images)"))
        }
        statements = []
        if "note" not in cols:
            statements.append("ALTER TABLE order_images ADD COLUMN note VARCHAR(255)")

        for stmt in statements:
            db.session.execute(text(stmt))
        if statements:
            db.session.commit()
    except Exception:
        app.logger.exception("Failed to ensure order_images columns exist")


def ensure_order_videos_table():
    """
    Ensures the order_videos table exists for project video uploads.
    """
    try:
        exists = db.session.execute(
            text("SELECT name FROM sqlite_master WHERE type='table' AND name='order_videos'")
        ).scalar()
        if exists:
            return

        db.session.execute(
            text(
                """
                CREATE TABLE order_videos (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    order_id INTEGER NOT NULL,
                    original_name VARCHAR(255) NOT NULL,
                    stored_name VARCHAR(255) NOT NULL,
                    file_type VARCHAR(20),
                    filesize INTEGER,
                    note VARCHAR(255),
                    uploaded_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
        )
        db.session.commit()
    except Exception:
        app.logger.exception("Failed to ensure order_videos table exists")


def ensure_training_videos_table():
    """
    Ensures the training_videos table and required columns exist.
    """
    try:
        exists = db.session.execute(
            text("SELECT name FROM sqlite_master WHERE type='table' AND name='training_videos'")
        ).scalar()
        if not exists:
            db.session.execute(
                text(
                    """
                    CREATE TABLE training_videos (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        title VARCHAR(200) NOT NULL,
                        description TEXT,
                        youtube_url VARCHAR(500) NOT NULL,
                        pdf_filename VARCHAR(255),
                        pdf_original_name VARCHAR(255),
                        pdf_filesize INTEGER,
                        sort_order INTEGER NOT NULL DEFAULT 0,
                        created_at DATETIME NOT NULL,
                        updated_at DATETIME NOT NULL
                    )
                    """
                )
            )
            db.session.commit()
            return

        cols = {
            row[1]
            for row in db.session.execute(text("PRAGMA table_info(training_videos)"))
        }
        statements = []
        if "sort_order" not in cols:
            statements.append("ALTER TABLE training_videos ADD COLUMN sort_order INTEGER NOT NULL DEFAULT 0")
        if "pdf_filename" not in cols:
            statements.append("ALTER TABLE training_videos ADD COLUMN pdf_filename VARCHAR(255)")
        if "pdf_original_name" not in cols:
            statements.append("ALTER TABLE training_videos ADD COLUMN pdf_original_name VARCHAR(255)")
        if "pdf_filesize" not in cols:
            statements.append("ALTER TABLE training_videos ADD COLUMN pdf_filesize INTEGER")

        for stmt in statements:
            db.session.execute(text(stmt))
        if statements:
            db.session.commit()
    except Exception:
        app.logger.exception("Failed to ensure training_videos table exists")


def ensure_printer_profiles_table():
    """
    Ensures the printer_profiles table and required columns exist.
    """
    try:
        exists = db.session.execute(
            text("SELECT name FROM sqlite_master WHERE type='table' AND name='printer_profiles'")
        ).scalar()
        if not exists:
            db.session.execute(
                text(
                    """
                    CREATE TABLE printer_profiles (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        name VARCHAR(100) NOT NULL UNIQUE,
                        description TEXT,
                        time_factor FLOAT NOT NULL DEFAULT 1.0,
                        time_offset_min INTEGER NOT NULL DEFAULT 0,
                        machine_hourly_rate FLOAT NOT NULL DEFAULT 0.0,
                        maintenance_hourly_rate FLOAT NOT NULL DEFAULT 0.0,
                        setup_fee FLOAT NOT NULL DEFAULT 0.0,
                        active BOOLEAN NOT NULL DEFAULT 1,
                        created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                    )
                    """
                )
            )
            db.session.commit()
            return

        cols = {
            row[1]
            for row in db.session.execute(text("PRAGMA table_info(printer_profiles)"))
        }
        statements = []
        if "description" not in cols:
            statements.append("ALTER TABLE printer_profiles ADD COLUMN description TEXT")
        if "time_factor" not in cols:
            statements.append("ALTER TABLE printer_profiles ADD COLUMN time_factor FLOAT NOT NULL DEFAULT 1.0")
        if "time_offset_min" not in cols:
            statements.append("ALTER TABLE printer_profiles ADD COLUMN time_offset_min INTEGER NOT NULL DEFAULT 0")
        if "machine_hourly_rate" not in cols:
            statements.append("ALTER TABLE printer_profiles ADD COLUMN machine_hourly_rate FLOAT NOT NULL DEFAULT 0.0")
        if "maintenance_hourly_rate" not in cols:
            statements.append("ALTER TABLE printer_profiles ADD COLUMN maintenance_hourly_rate FLOAT NOT NULL DEFAULT 0.0")
        if "setup_fee" not in cols:
            statements.append("ALTER TABLE printer_profiles ADD COLUMN setup_fee FLOAT NOT NULL DEFAULT 0.0")
        if "active" not in cols:
            statements.append("ALTER TABLE printer_profiles ADD COLUMN active BOOLEAN NOT NULL DEFAULT 1")
        if "created_at" not in cols:
            statements.append(
                "ALTER TABLE printer_profiles ADD COLUMN created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP"
            )
        if "updated_at" not in cols:
            statements.append(
                "ALTER TABLE printer_profiles ADD COLUMN updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP"
            )

        for stmt in statements:
            db.session.execute(text(stmt))
        if statements:
            db.session.commit()
    except Exception:
        app.logger.exception("Failed to ensure printer_profiles table exists")


def ensure_filament_materials_table():
    """
    Ensures the filament_materials table and required columns exist.
    """
    try:
        exists = db.session.execute(
            text("SELECT name FROM sqlite_master WHERE type='table' AND name='filament_materials'")
        ).scalar()
        if not exists:
            db.session.execute(
                text(
                    """
                    CREATE TABLE filament_materials (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        name VARCHAR(50) NOT NULL UNIQUE,
                        filament_diameter_mm FLOAT NOT NULL DEFAULT 1.75,
                        density_g_cm3 FLOAT NOT NULL DEFAULT 1.0,
                        description TEXT,
                        price_per_kg FLOAT NOT NULL DEFAULT 0.0,
                        markup_percent FLOAT NOT NULL DEFAULT 0.0,
                        drying_fee FLOAT NOT NULL DEFAULT 0.0,
                        handling_fee FLOAT NOT NULL DEFAULT 0.0,
                        active BOOLEAN NOT NULL DEFAULT 1,
                        created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                    )
                    """
                )
            )
            db.session.commit()
            return

        cols = {
            row[1]
            for row in db.session.execute(text("PRAGMA table_info(filament_materials)"))
        }
        statements = []
        if "filament_diameter_mm" not in cols:
            statements.append(
                "ALTER TABLE filament_materials ADD COLUMN filament_diameter_mm FLOAT NOT NULL DEFAULT 1.75"
            )
        if "density_g_cm3" not in cols:
            statements.append("ALTER TABLE filament_materials ADD COLUMN density_g_cm3 FLOAT NOT NULL DEFAULT 1.0")
        if "description" not in cols:
            statements.append("ALTER TABLE filament_materials ADD COLUMN description TEXT")
        if "price_per_kg" not in cols:
            statements.append("ALTER TABLE filament_materials ADD COLUMN price_per_kg FLOAT NOT NULL DEFAULT 0.0")
        if "markup_percent" not in cols:
            statements.append("ALTER TABLE filament_materials ADD COLUMN markup_percent FLOAT NOT NULL DEFAULT 0.0")
        if "drying_fee" not in cols:
            statements.append("ALTER TABLE filament_materials ADD COLUMN drying_fee FLOAT NOT NULL DEFAULT 0.0")
        if "handling_fee" not in cols:
            statements.append("ALTER TABLE filament_materials ADD COLUMN handling_fee FLOAT NOT NULL DEFAULT 0.0")
        if "active" not in cols:
            statements.append("ALTER TABLE filament_materials ADD COLUMN active BOOLEAN NOT NULL DEFAULT 1")
        if "created_at" not in cols:
            statements.append(
                "ALTER TABLE filament_materials ADD COLUMN created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP"
            )
        if "updated_at" not in cols:
            statements.append(
                "ALTER TABLE filament_materials ADD COLUMN updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP"
            )

        for stmt in statements:
            db.session.execute(text(stmt))
        if statements:
            db.session.commit()
    except Exception:
        app.logger.exception("Failed to ensure filament_materials table exists")


def ensure_order_estimation_columns():
    """
    Adds missing estimation-related columns on orders (lightweight migration).
    """
    try:
        exists = db.session.execute(
            text("SELECT name FROM sqlite_master WHERE type='table' AND name='orders'")
        ).scalar()
        if not exists:
            return

        cols = {
            row[1]
            for row in db.session.execute(text("PRAGMA table_info(orders)"))
        }
        statements = []
        if "printer_profile_id" not in cols:
            statements.append("ALTER TABLE orders ADD COLUMN printer_profile_id INTEGER")
        if "filament_material_id" not in cols:
            statements.append("ALTER TABLE orders ADD COLUMN filament_material_id INTEGER")
        if "est_filament_m" not in cols:
            statements.append("ALTER TABLE orders ADD COLUMN est_filament_m FLOAT")
        if "est_filament_g" not in cols:
            statements.append("ALTER TABLE orders ADD COLUMN est_filament_g FLOAT")
        if "est_time_s" not in cols:
            statements.append("ALTER TABLE orders ADD COLUMN est_time_s INTEGER")
        if "est_time_s_with_margin" not in cols:
            statements.append("ALTER TABLE orders ADD COLUMN est_time_s_with_margin INTEGER")
        if "est_method" not in cols:
            statements.append("ALTER TABLE orders ADD COLUMN est_method VARCHAR(50)")

        for stmt in statements:
            db.session.execute(text(stmt))
        if statements:
            db.session.commit()
    except Exception:
        app.logger.exception("Failed to ensure orders estimation columns exist")


def ensure_order_project_columns():
    """
    Adds missing project/publication-related columns on orders (lightweight migration).
    """
    try:
        exists = db.session.execute(
            text("SELECT name FROM sqlite_master WHERE type='table' AND name='orders'")
        ).scalar()
        if not exists:
            return

        cols = {
            row[1]
            for row in db.session.execute(text("PRAGMA table_info(orders)"))
        }
        statements = []
        if "public_allow_poster" not in cols:
            statements.append("ALTER TABLE orders ADD COLUMN public_allow_poster BOOLEAN NOT NULL DEFAULT 1")
        if "public_allow_web" not in cols:
            statements.append("ALTER TABLE orders ADD COLUMN public_allow_web BOOLEAN NOT NULL DEFAULT 1")
        if "public_allow_social" not in cols:
            statements.append("ALTER TABLE orders ADD COLUMN public_allow_social BOOLEAN NOT NULL DEFAULT 1")
        if "public_display_name" not in cols:
            statements.append("ALTER TABLE orders ADD COLUMN public_display_name VARCHAR(200)")
        if "summary_short" not in cols:
            statements.append("ALTER TABLE orders ADD COLUMN summary_short VARCHAR(255)")
        if "summary_long" not in cols:
            statements.append("ALTER TABLE orders ADD COLUMN summary_long TEXT")
        if "project_group" not in cols:
            statements.append("ALTER TABLE orders ADD COLUMN project_group VARCHAR(255)")
        if "project_purpose" not in cols:
            statements.append("ALTER TABLE orders ADD COLUMN project_purpose VARCHAR(255)")
        if "project_use_case" not in cols:
            statements.append("ALTER TABLE orders ADD COLUMN project_use_case VARCHAR(255)")
        if "learning_points" not in cols:
            statements.append("ALTER TABLE orders ADD COLUMN learning_points TEXT")
        if "background_info" not in cols:
            statements.append("ALTER TABLE orders ADD COLUMN background_info TEXT")
        if "project_url" not in cols:
            statements.append("ALTER TABLE orders ADD COLUMN project_url VARCHAR(500)")

        for stmt in statements:
            db.session.execute(text(stmt))
        if statements:
            db.session.commit()
    except Exception:
        app.logger.exception("Failed to ensure orders project columns exist")


def ensure_order_archive_columns():
    """
    Adds archive columns on orders (lightweight migration).
    """
    try:
        exists = db.session.execute(
            text("SELECT name FROM sqlite_master WHERE type='table' AND name='orders'")
        ).scalar()
        if not exists:
            return

        cols = {
            row[1]
            for row in db.session.execute(text("PRAGMA table_info(orders)"))
        }
        statements = []
        if "is_archived" not in cols:
            statements.append("ALTER TABLE orders ADD COLUMN is_archived BOOLEAN NOT NULL DEFAULT 0")
        if "archived_at" not in cols:
            statements.append("ALTER TABLE orders ADD COLUMN archived_at DATETIME")

        for stmt in statements:
            db.session.execute(text(stmt))
        if statements:
            db.session.commit()
    except Exception:
        app.logger.exception("Failed to ensure orders archive columns exist")


def ensure_order_category_schema():
    """
    Ensures order categories, generic work jobs and user category permissions exist.
    """
    try:
        exists = db.session.execute(
            text("SELECT name FROM sqlite_master WHERE type='table' AND name='order_categories'")
        ).scalar()
        if not exists:
            db.session.execute(
                text(
                    """
                    CREATE TABLE order_categories (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        key VARCHAR(50) NOT NULL UNIQUE,
                        name VARCHAR(100) NOT NULL,
                        description TEXT,
                        enabled_tabs VARCHAR(255) NOT NULL DEFAULT 'general,files,communication',
                        allowed_worker_roles VARCHAR(255) NOT NULL DEFAULT 'admin',
                        active BOOLEAN NOT NULL DEFAULT 1,
                        created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                    )
                    """
                )
            )
            db.session.commit()
        else:
            cols = {
                row[1]
                for row in db.session.execute(text("PRAGMA table_info(order_categories)"))
            }
            statements = []
            if "description" not in cols:
                statements.append("ALTER TABLE order_categories ADD COLUMN description TEXT")
            if "enabled_tabs" not in cols:
                statements.append(
                    "ALTER TABLE order_categories ADD COLUMN enabled_tabs VARCHAR(255) NOT NULL DEFAULT 'general,files,communication'"
                )
            if "allowed_worker_roles" not in cols:
                statements.append(
                    "ALTER TABLE order_categories ADD COLUMN allowed_worker_roles VARCHAR(255) NOT NULL DEFAULT 'admin'"
                )
            if "active" not in cols:
                statements.append("ALTER TABLE order_categories ADD COLUMN active BOOLEAN NOT NULL DEFAULT 1")
            if "created_at" not in cols:
                statements.append(
                    "ALTER TABLE order_categories ADD COLUMN created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP"
                )
            if "updated_at" not in cols:
                statements.append(
                    "ALTER TABLE order_categories ADD COLUMN updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP"
                )
            for stmt in statements:
                db.session.execute(text(stmt))
            if statements:
                db.session.commit()

        orders_exists = db.session.execute(
            text("SELECT name FROM sqlite_master WHERE type='table' AND name='orders'")
        ).scalar()
        if orders_exists:
            order_cols = {
                row[1]
                for row in db.session.execute(text("PRAGMA table_info(orders)"))
            }
            if "category_id" not in order_cols:
                db.session.execute(text("ALTER TABLE orders ADD COLUMN category_id INTEGER"))
                db.session.commit()

        work_jobs_exists = db.session.execute(
            text("SELECT name FROM sqlite_master WHERE type='table' AND name='order_work_jobs'")
        ).scalar()
        if not work_jobs_exists:
            db.session.execute(
                text(
                    """
                    CREATE TABLE order_work_jobs (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        order_id INTEGER NOT NULL,
                        category_id INTEGER,
                        status VARCHAR(50) NOT NULL DEFAULT 'upload',
                        machine_name VARCHAR(100),
                        material_note VARCHAR(255),
                        cost_amount FLOAT,
                        note VARCHAR(255),
                        started_at DATETIME,
                        duration_min INTEGER,
                        created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                    )
                    """
                )
            )
            db.session.commit()

        permission_exists = db.session.execute(
            text("SELECT name FROM sqlite_master WHERE type='table' AND name='user_order_category_permissions'")
        ).scalar()
        if not permission_exists:
            db.session.execute(
                text(
                    """
                    CREATE TABLE user_order_category_permissions (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id INTEGER NOT NULL,
                        category_id INTEGER NOT NULL,
                        can_manage BOOLEAN NOT NULL DEFAULT 1,
                        UNIQUE(user_id, category_id)
                    )
                    """
                )
            )
            db.session.commit()

        for item in DEFAULT_ORDER_CATEGORIES:
            existing = OrderCategory.query.filter_by(key=item["key"]).first()
            if existing:
                if existing.enabled_tabs != item["enabled_tabs"]:
                    existing.enabled_tabs = item["enabled_tabs"]
                    existing.updated_at = datetime.utcnow()
                if existing.name != item["name"]:
                    existing.name = item["name"]
                    existing.updated_at = datetime.utcnow()
                if existing.description != item["description"]:
                    existing.description = item["description"]
                    existing.updated_at = datetime.utcnow()
                if existing.allowed_worker_roles != item["allowed_worker_roles"]:
                    existing.allowed_worker_roles = item["allowed_worker_roles"]
                    existing.updated_at = datetime.utcnow()
                continue
            db.session.add(OrderCategory(**item))
        db.session.commit()

        user_exists = db.session.execute(
            text("SELECT name FROM sqlite_master WHERE type='table' AND name='user'")
        ).scalar()
        if user_exists:
            db.session.execute(
                text(
                    """
                    UPDATE user
                    SET role = 'worker'
                    WHERE role IN ('worker_3d_print', 'worker_plotter', 'worker_cnc')
                    """
                )
            )
            db.session.commit()

        default_category = OrderCategory.query.filter_by(key="3d_print").first()
        if default_category and orders_exists:
            db.session.execute(
                text("UPDATE orders SET category_id = :category_id WHERE category_id IS NULL"),
                {"category_id": default_category.id},
            )
            db.session.commit()

        poster_files_exists = db.session.execute(
            text("SELECT name FROM sqlite_master WHERE type='table' AND name='order_poster_files'")
        ).scalar()
        if not poster_files_exists:
            db.session.execute(
                text(
                    """
                    CREATE TABLE order_poster_files (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        order_id INTEGER NOT NULL,
                        original_name VARCHAR(255) NOT NULL,
                        stored_name VARCHAR(255) NOT NULL,
                        file_type VARCHAR(20),
                        filesize INTEGER,
                        note VARCHAR(255),
                        status VARCHAR(50) NOT NULL DEFAULT 'open',
                        quantity INTEGER NOT NULL DEFAULT 1,
                        due_date DATE,
                        thumb_path VARCHAR(255),
                        uploaded_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                    )
                    """
                )
            )
            db.session.commit()
        else:
            poster_cols = {
                row[1]
                for row in db.session.execute(text("PRAGMA table_info(order_poster_files)"))
            }
            if "thumb_path" not in poster_cols:
                db.session.execute(text("ALTER TABLE order_poster_files ADD COLUMN thumb_path VARCHAR(255)"))
                db.session.commit()
            if "status" not in poster_cols:
                db.session.execute(
                    text("ALTER TABLE order_poster_files ADD COLUMN status VARCHAR(50) NOT NULL DEFAULT 'open'")
                )
                db.session.commit()

        procurement_articles_exists = db.session.execute(
            text("SELECT name FROM sqlite_master WHERE type='table' AND name='order_procurement_articles'")
        ).scalar()
        if not procurement_articles_exists:
            db.session.execute(
                text(
                    """
                    CREATE TABLE order_procurement_articles (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        order_id INTEGER NOT NULL,
                        article_name VARCHAR(255) NOT NULL,
                        status VARCHAR(50) NOT NULL DEFAULT 'open',
                        article_description TEXT,
                        supplier VARCHAR(255),
                        article_url VARCHAR(1000),
                        position_number INTEGER,
                        quantity INTEGER NOT NULL DEFAULT 1,
                        price_per_unit_incl_vat FLOAT,
                        note_file_original_name VARCHAR(255),
                        note_file_stored_name VARCHAR(255),
                        note_file_type VARCHAR(20),
                        note_file_size INTEGER,
                        created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                    )
                    """
                )
            )
            db.session.commit()
        else:
            procurement_cols = {
                row[1]
                for row in db.session.execute(text("PRAGMA table_info(order_procurement_articles)"))
            }
            procurement_statements = []
            if "article_description" not in procurement_cols:
                procurement_statements.append("ALTER TABLE order_procurement_articles ADD COLUMN article_description TEXT")
            if "status" not in procurement_cols:
                procurement_statements.append(
                    "ALTER TABLE order_procurement_articles ADD COLUMN status VARCHAR(50) NOT NULL DEFAULT 'open'"
                )
            if "supplier" not in procurement_cols:
                procurement_statements.append("ALTER TABLE order_procurement_articles ADD COLUMN supplier VARCHAR(255)")
            if "article_url" not in procurement_cols:
                procurement_statements.append("ALTER TABLE order_procurement_articles ADD COLUMN article_url VARCHAR(1000)")
            if "position_number" not in procurement_cols:
                procurement_statements.append("ALTER TABLE order_procurement_articles ADD COLUMN position_number INTEGER")
            if "quantity" not in procurement_cols:
                procurement_statements.append(
                    "ALTER TABLE order_procurement_articles ADD COLUMN quantity INTEGER NOT NULL DEFAULT 1"
                )
            if "price_per_unit_incl_vat" not in procurement_cols:
                procurement_statements.append(
                    "ALTER TABLE order_procurement_articles ADD COLUMN price_per_unit_incl_vat FLOAT"
                )
            if "note_file_original_name" not in procurement_cols:
                procurement_statements.append(
                    "ALTER TABLE order_procurement_articles ADD COLUMN note_file_original_name VARCHAR(255)"
                )
            if "note_file_stored_name" not in procurement_cols:
                procurement_statements.append(
                    "ALTER TABLE order_procurement_articles ADD COLUMN note_file_stored_name VARCHAR(255)"
                )
            if "note_file_type" not in procurement_cols:
                procurement_statements.append(
                    "ALTER TABLE order_procurement_articles ADD COLUMN note_file_type VARCHAR(20)"
                )
            if "note_file_size" not in procurement_cols:
                procurement_statements.append(
                    "ALTER TABLE order_procurement_articles ADD COLUMN note_file_size INTEGER"
                )
            if "created_at" not in procurement_cols:
                procurement_statements.append(
                    "ALTER TABLE order_procurement_articles ADD COLUMN created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP"
                )
            if "updated_at" not in procurement_cols:
                procurement_statements.append(
                    "ALTER TABLE order_procurement_articles ADD COLUMN updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP"
                )
            for stmt in procurement_statements:
                db.session.execute(text(stmt))
            if procurement_statements:
                db.session.commit()
            if "position_number" not in procurement_cols:
                order_ids = [
                    row[0]
                    for row in db.session.execute(
                        text("SELECT DISTINCT order_id FROM order_procurement_articles ORDER BY order_id")
                    )
                ]
                for order_id in order_ids:
                    ensure_procurement_article_position_numbers(order_id)
                if order_ids:
                    db.session.commit()
    except Exception:
        app.logger.exception("Failed to ensure order category schema exists")


def ensure_order_area_schema():
    """
    Ensures order areas and user dashboard area preferences exist.
    """
    try:
        areas_exists = db.session.execute(
            text("SELECT name FROM sqlite_master WHERE type='table' AND name='order_areas'")
        ).scalar()
        if not areas_exists:
            db.session.execute(
                text(
                    """
                    CREATE TABLE order_areas (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        name VARCHAR(120) NOT NULL UNIQUE,
                        short_name VARCHAR(30) NOT NULL UNIQUE,
                        created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                    )
                    """
                )
            )
            db.session.commit()

        area_cols = {
            row[1]
            for row in db.session.execute(text("PRAGMA table_info(order_areas)"))
        }
        if "short_name" not in area_cols:
            db.session.execute(text("ALTER TABLE order_areas ADD COLUMN short_name VARCHAR(30)"))
            db.session.execute(
                text(
                    """
                    UPDATE order_areas
                    SET short_name = name
                    WHERE short_name IS NULL OR TRIM(short_name) = ''
                    """
                )
            )
            db.session.execute(
                text(
                    """
                    CREATE UNIQUE INDEX IF NOT EXISTS uq_order_areas_short_name
                    ON order_areas(short_name)
                    """
                )
            )
            db.session.commit()

        orders_exists = db.session.execute(
            text("SELECT name FROM sqlite_master WHERE type='table' AND name='orders'")
        ).scalar()
        if orders_exists:
            order_cols = {
                row[1]
                for row in db.session.execute(text("PRAGMA table_info(orders)"))
            }
            if "area_id" not in order_cols:
                db.session.execute(text("ALTER TABLE orders ADD COLUMN area_id INTEGER"))
                db.session.commit()

        prefs_exists = db.session.execute(
            text("SELECT name FROM sqlite_master WHERE type='table' AND name='user_order_area_preferences'")
        ).scalar()
        if not prefs_exists:
            db.session.execute(
                text(
                    """
                    CREATE TABLE user_order_area_preferences (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id INTEGER NOT NULL,
                        area_id INTEGER NOT NULL,
                        UNIQUE(user_id, area_id)
                    )
                    """
                )
            )
            db.session.commit()

        if not OrderArea.query.first():
            db.session.add(OrderArea(name="Standard", short_name="Standard"))
            db.session.commit()
    except Exception:
        app.logger.exception("Failed to ensure order area schema exists")


def ensure_order_print_jobs_table():
    """
    Ensures the order_print_jobs table and required columns exist.
    """
    try:
        exists = db.session.execute(
            text("SELECT name FROM sqlite_master WHERE type='table' AND name='order_print_jobs'")
        ).scalar()
        if not exists:
            db.session.execute(
                text(
                    """
                    CREATE TABLE order_print_jobs (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        order_id INTEGER NOT NULL,
                        printer_profile_id INTEGER,
                        filament_material_id INTEGER,
                        original_name VARCHAR(255) NOT NULL,
                        stored_name VARCHAR(255) NOT NULL,
                        note VARCHAR(255),
                        status VARCHAR(50) NOT NULL DEFAULT 'upload',
                        started_at DATETIME,
                        duration_min INTEGER,
                        filament_m FLOAT,
                        filament_g FLOAT,
                        quantity INTEGER NOT NULL DEFAULT 1,
                        filesize INTEGER,
                        uploaded_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                    )
                    """
                )
            )
            db.session.commit()
            return

        cols = {
            row[1]
            for row in db.session.execute(text("PRAGMA table_info(order_print_jobs)"))
        }
        statements = []
        if "note" not in cols:
            statements.append("ALTER TABLE order_print_jobs ADD COLUMN note VARCHAR(255)")
        add_printer_profile_id = "printer_profile_id" not in cols
        add_filament_material_id = "filament_material_id" not in cols
        if add_printer_profile_id:
            statements.append("ALTER TABLE order_print_jobs ADD COLUMN printer_profile_id INTEGER")
        if add_filament_material_id:
            statements.append("ALTER TABLE order_print_jobs ADD COLUMN filament_material_id INTEGER")
        if "status" not in cols:
            statements.append("ALTER TABLE order_print_jobs ADD COLUMN status VARCHAR(50) NOT NULL DEFAULT 'upload'")
        if "started_at" not in cols:
            statements.append("ALTER TABLE order_print_jobs ADD COLUMN started_at DATETIME")
        if "duration_min" not in cols:
            statements.append("ALTER TABLE order_print_jobs ADD COLUMN duration_min INTEGER")
        if "filament_m" not in cols:
            statements.append("ALTER TABLE order_print_jobs ADD COLUMN filament_m FLOAT")
        if "filament_g" not in cols:
            statements.append("ALTER TABLE order_print_jobs ADD COLUMN filament_g FLOAT")
        if "quantity" not in cols:
            statements.append("ALTER TABLE order_print_jobs ADD COLUMN quantity INTEGER NOT NULL DEFAULT 1")
        if "filesize" not in cols:
            statements.append("ALTER TABLE order_print_jobs ADD COLUMN filesize INTEGER")
        if "uploaded_at" not in cols:
            statements.append(
                "ALTER TABLE order_print_jobs ADD COLUMN uploaded_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP"
            )

        for stmt in statements:
            db.session.execute(text(stmt))
        if statements:
            if add_printer_profile_id:
                db.session.execute(
                    text(
                        """
                        UPDATE order_print_jobs
                        SET printer_profile_id = (
                            SELECT printer_profile_id FROM orders WHERE orders.id = order_print_jobs.order_id
                        )
                        WHERE printer_profile_id IS NULL
                        """
                    )
                )
            if add_filament_material_id:
                db.session.execute(
                    text(
                        """
                        UPDATE order_print_jobs
                        SET filament_material_id = (
                            SELECT filament_material_id FROM orders WHERE orders.id = order_print_jobs.order_id
                        )
                        WHERE filament_material_id IS NULL
                        """
                    )
                )
            db.session.commit()
    except Exception:
        app.logger.exception("Failed to ensure order_print_jobs table exists")


def ensure_announcements_table():
    """
    Ensures the announcements table and required columns exist.
    """
    try:
        exists = db.session.execute(
            text("SELECT name FROM sqlite_master WHERE type='table' AND name='announcements'")
        ).scalar()
        if not exists:
            db.session.execute(
                text(
                    """
                    CREATE TABLE announcements (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        title VARCHAR(200) NOT NULL,
                        body TEXT NOT NULL,
                        priority VARCHAR(20) NOT NULL DEFAULT 'info',
                        created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        created_by_id INTEGER,
                        updated_by_id INTEGER
                    )
                    """
                )
            )
            db.session.commit()
            return

        cols = {
            row[1]
            for row in db.session.execute(text("PRAGMA table_info(announcements)"))
        }
        statements = []
        if "title" not in cols:
            statements.append("ALTER TABLE announcements ADD COLUMN title VARCHAR(200) NOT NULL DEFAULT ''")
        if "body" not in cols:
            statements.append("ALTER TABLE announcements ADD COLUMN body TEXT NOT NULL DEFAULT ''")
        if "priority" not in cols:
            statements.append("ALTER TABLE announcements ADD COLUMN priority VARCHAR(20) NOT NULL DEFAULT 'info'")
        if "created_at" not in cols:
            statements.append(
                "ALTER TABLE announcements ADD COLUMN created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP"
            )
        if "updated_at" not in cols:
            statements.append(
                "ALTER TABLE announcements ADD COLUMN updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP"
            )
        if "created_by_id" not in cols:
            statements.append("ALTER TABLE announcements ADD COLUMN created_by_id INTEGER")
        if "updated_by_id" not in cols:
            statements.append("ALTER TABLE announcements ADD COLUMN updated_by_id INTEGER")

        for stmt in statements:
            db.session.execute(text(stmt))
        if statements:
            db.session.commit()
    except Exception:
        app.logger.exception("Failed to ensure announcements table exists")


def ensure_announcement_reads_table():
    """
    Ensures the announcement_reads table and required columns exist.
    """
    try:
        exists = db.session.execute(
            text("SELECT name FROM sqlite_master WHERE type='table' AND name='announcement_reads'")
        ).scalar()
        if not exists:
            db.session.execute(
                text(
                    """
                    CREATE TABLE announcement_reads (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        announcement_id INTEGER NOT NULL,
                        user_id INTEGER NOT NULL,
                        read_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        UNIQUE(announcement_id, user_id)
                    )
                    """
                )
            )
            db.session.commit()
            return

        cols = {
            row[1]
            for row in db.session.execute(text("PRAGMA table_info(announcement_reads)"))
        }
        statements = []
        if "announcement_id" not in cols:
            statements.append("ALTER TABLE announcement_reads ADD COLUMN announcement_id INTEGER NOT NULL DEFAULT 0")
        if "user_id" not in cols:
            statements.append("ALTER TABLE announcement_reads ADD COLUMN user_id INTEGER NOT NULL DEFAULT 0")
        if "read_at" not in cols:
            statements.append(
                "ALTER TABLE announcement_reads ADD COLUMN read_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP"
            )

        for stmt in statements:
            db.session.execute(text(stmt))
        if statements:
            db.session.commit()
    except Exception:
        app.logger.exception("Failed to ensure announcement_reads table exists")


def ensure_order_read_status_table():
    """
    Ensures the persistent per-user order read status table exists.
    """
    try:
        exists = db.session.execute(
            text("SELECT name FROM sqlite_master WHERE type='table' AND name='order_read_status'")
        ).scalar()
        if not exists:
            db.session.execute(
                text(
                    """
                    CREATE TABLE order_read_status (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        order_id INTEGER NOT NULL,
                        user_id INTEGER NOT NULL,
                        last_read_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        UNIQUE(order_id, user_id)
                    )
                    """
                )
            )
            db.session.commit()
            return

        cols = {
            row[1]
            for row in db.session.execute(text("PRAGMA table_info(order_read_status)"))
        }
        statements = []
        if "order_id" not in cols:
            statements.append("ALTER TABLE order_read_status ADD COLUMN order_id INTEGER NOT NULL DEFAULT 0")
        if "user_id" not in cols:
            statements.append("ALTER TABLE order_read_status ADD COLUMN user_id INTEGER NOT NULL DEFAULT 0")
        if "last_read_at" not in cols:
            statements.append(
                "ALTER TABLE order_read_status ADD COLUMN last_read_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP"
            )

        for stmt in statements:
            db.session.execute(text(stmt))
        if statements:
            db.session.commit()
    except Exception:
        app.logger.exception("Failed to ensure order_read_status table exists")


def ensure_user_status_columns():
    """
    Adds lightweight user status columns used for deactivate/soft-delete.
    """
    try:
        exists = db.session.execute(
            text("SELECT name FROM sqlite_master WHERE type='table' AND name='user'")
        ).scalar()
        if not exists:
            return

        cols = {
            row[1]
            for row in db.session.execute(text("PRAGMA table_info(user)"))
        }
        statements = []
        if "is_active" not in cols:
            statements.append("ALTER TABLE user ADD COLUMN is_active BOOLEAN NOT NULL DEFAULT 1")
        if "deleted_at" not in cols:
            statements.append("ALTER TABLE user ADD COLUMN deleted_at DATETIME")

        for stmt in statements:
            db.session.execute(text(stmt))
        if statements:
            db.session.commit()
    except Exception:
        app.logger.exception("Failed to ensure user status columns exist")


def ensure_user_preference_columns():
    """
    Adds user preference columns used by profile settings.
    """
    try:
        exists = db.session.execute(
            text("SELECT name FROM sqlite_master WHERE type='table' AND name='user'")
        ).scalar()
        if not exists:
            return

        cols = {
            row[1]
            for row in db.session.execute(text("PRAGMA table_info(user)"))
        }
        statements = []
        if "theme_mode" not in cols:
            statements.append("ALTER TABLE user ADD COLUMN theme_mode VARCHAR(10) NOT NULL DEFAULT 'light'")
        if "status_email_enabled" not in cols:
            statements.append("ALTER TABLE user ADD COLUMN status_email_enabled BOOLEAN NOT NULL DEFAULT 1")

        for stmt in statements:
            db.session.execute(text(stmt))
        if statements:
            db.session.commit()
    except Exception:
        app.logger.exception("Failed to ensure user preference columns exist")


def ensure_user_email_favorites_table():
    """
    Ensures per-user email favorites for reusable address suggestions exist.
    """
    try:
        exists = db.session.execute(
            text("SELECT name FROM sqlite_master WHERE type='table' AND name='user_email_favorites'")
        ).scalar()
        if not exists:
            db.session.execute(
                text(
                    """
                    CREATE TABLE IF NOT EXISTS user_email_favorites (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id INTEGER NOT NULL,
                        email VARCHAR(255) NOT NULL,
                        created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        UNIQUE(user_id, email)
                    )
                    """
                )
            )
            db.session.commit()
            return

        cols = {
            row[1]
            for row in db.session.execute(text("PRAGMA table_info(user_email_favorites)"))
        }
        statements = []
        if "user_id" not in cols:
            statements.append("ALTER TABLE user_email_favorites ADD COLUMN user_id INTEGER NOT NULL DEFAULT 0")
        if "email" not in cols:
            statements.append("ALTER TABLE user_email_favorites ADD COLUMN email VARCHAR(255) NOT NULL DEFAULT ''")
        if "created_at" not in cols:
            statements.append(
                "ALTER TABLE user_email_favorites ADD COLUMN created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP"
            )

        for stmt in statements:
            db.session.execute(text(stmt))
        if statements:
            db.session.commit()
    except Exception:
        app.logger.exception("Failed to ensure user_email_favorites table exists")


def split_email_recipients(raw: str | None) -> list[str]:
    if not raw:
        return []
    normalized = raw.replace(";", ",").replace("\n", ",").replace("\r", ",")
    recipients: list[str] = []
    seen: set[str] = set()
    for _, email in getaddresses([normalized]):
        email = (email or "").strip()
        if not email or "@" not in email:
            continue
        key = email.lower()
        if key in seen:
            continue
        recipients.append(email)
        seen.add(key)
    return recipients


def save_user_email_favorites(user_id: int, raw_recipients: str | None) -> None:
    for email in split_email_recipients(raw_recipients):
        normalized_email = email.strip().lower()
        exists = UserEmailFavorite.query.filter_by(
            user_id=user_id,
            email=normalized_email,
        ).first()
        if exists:
            continue
        db.session.add(
            UserEmailFavorite(
                user_id=user_id,
                email=normalized_email,
            )
        )


def ensure_user_activation_tokens_table():
    """
    Ensures the account activation token table exists.
    """
    try:
        exists = db.session.execute(
            text("SELECT name FROM sqlite_master WHERE type='table' AND name='user_activation_tokens'")
        ).scalar()
        if not exists:
            db.session.execute(
                text(
                    """
                    CREATE TABLE user_activation_tokens (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id INTEGER NOT NULL,
                        token_hash VARCHAR(64) NOT NULL UNIQUE,
                        source VARCHAR(50),
                        expires_at DATETIME NOT NULL,
                        used_at DATETIME,
                        created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                    )
                    """
                )
            )
            db.session.commit()
            return

        cols = {
            row[1]
            for row in db.session.execute(text("PRAGMA table_info(user_activation_tokens)"))
        }
        statements = []
        if "user_id" not in cols:
            statements.append("ALTER TABLE user_activation_tokens ADD COLUMN user_id INTEGER NOT NULL DEFAULT 0")
        if "token_hash" not in cols:
            statements.append("ALTER TABLE user_activation_tokens ADD COLUMN token_hash VARCHAR(64) NOT NULL DEFAULT ''")
        if "source" not in cols:
            statements.append("ALTER TABLE user_activation_tokens ADD COLUMN source VARCHAR(50)")
        if "expires_at" not in cols:
            statements.append("ALTER TABLE user_activation_tokens ADD COLUMN expires_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP")
        if "used_at" not in cols:
            statements.append("ALTER TABLE user_activation_tokens ADD COLUMN used_at DATETIME")
        if "created_at" not in cols:
            statements.append("ALTER TABLE user_activation_tokens ADD COLUMN created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP")

        for stmt in statements:
            db.session.execute(text(stmt))
        if statements:
            db.session.commit()
    except Exception:
        app.logger.exception("Failed to ensure user activation token table exists")


def ensure_user_password_reset_tokens_table():
    """
    Ensures the password reset token table exists.
    """
    try:
        exists = db.session.execute(
            text("SELECT name FROM sqlite_master WHERE type='table' AND name='user_password_reset_tokens'")
        ).scalar()
        if not exists:
            db.session.execute(
                text(
                    """
                    CREATE TABLE user_password_reset_tokens (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id INTEGER NOT NULL,
                        token_hash VARCHAR(64) NOT NULL UNIQUE,
                        expires_at DATETIME NOT NULL,
                        used_at DATETIME,
                        created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                    )
                    """
                )
            )
            db.session.commit()
            return

        cols = {
            row[1]
            for row in db.session.execute(text("PRAGMA table_info(user_password_reset_tokens)"))
        }
        statements = []
        if "user_id" not in cols:
            statements.append("ALTER TABLE user_password_reset_tokens ADD COLUMN user_id INTEGER NOT NULL DEFAULT 0")
        if "token_hash" not in cols:
            statements.append("ALTER TABLE user_password_reset_tokens ADD COLUMN token_hash VARCHAR(64) NOT NULL DEFAULT ''")
        if "expires_at" not in cols:
            statements.append("ALTER TABLE user_password_reset_tokens ADD COLUMN expires_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP")
        if "used_at" not in cols:
            statements.append("ALTER TABLE user_password_reset_tokens ADD COLUMN used_at DATETIME")
        if "created_at" not in cols:
            statements.append("ALTER TABLE user_password_reset_tokens ADD COLUMN created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP")

        for stmt in statements:
            db.session.execute(text(stmt))
        if statements:
            db.session.commit()
    except Exception:
        app.logger.exception("Failed to ensure password reset token table exists")


with app.app_context():
    ensure_user_preference_columns()
    ensure_user_email_favorites_table()
    ensure_user_status_columns()
    ensure_user_activation_tokens_table()
    ensure_user_password_reset_tokens_table()
    ensure_order_file_columns()
    ensure_order_image_columns()
    ensure_order_videos_table()
    ensure_training_videos_table()
    ensure_printer_profiles_table()
    ensure_filament_materials_table()
    ensure_order_project_columns()
    ensure_order_estimation_columns()
    ensure_order_archive_columns()
    ensure_order_category_schema()
    ensure_order_area_schema()
    ensure_order_print_jobs_table()
    ensure_order_read_status_table()
    ensure_announcements_table()
    ensure_announcement_reads_table()
    ensure_order_id_sequence_table()
    maybe_cleanup_expired_logs(app, force=True)


def save_image_thumbnail(source_path: Path, target_path: Path, max_width: int = THUMBNAIL_MAX_WIDTH) -> bool:
    """
    Create a thumbnail at most `max_width` pixels wide while keeping aspect ratio.
    Stores the result at `target_path`. Returns True on success, False otherwise.
    """
    target_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with Image.open(source_path) as img:
            width, height = img.size
            if width <= 0 or height <= 0:
                raise ValueError("Invalid image dimensions")

            if width > max_width:
                new_height = max(1, int(height * (max_width / float(width))))
                img = img.resize((max_width, new_height), Image.LANCZOS)

            save_format = img.format or "PNG"
            if save_format.upper() in {"JPEG", "JPG"} and img.mode in {"RGBA", "LA", "P"}:
                img = img.convert("RGB")

            img.save(target_path, format=save_format)
        return True
    except Exception as exc:  # noqa: BLE001 - log and continue without blocking the upload
        app.logger.warning("Could not create thumbnail for %s: %s", source_path, exc)
        return False


def save_poster_thumbnail(source_path: Path, target_path: Path, file_type: str | None) -> bool:
    """
    Stores a poster thumbnail as PNG. PDFs are rendered with PyMuPDF when
    available; otherwise a neutral PDF placeholder is generated.
    """
    target_path.parent.mkdir(parents=True, exist_ok=True)
    ext = (file_type or "").lower()
    try:
        if ext in {"jpg", "jpeg", "png"}:
            with Image.open(source_path) as img:
                preview = _fit_image_to_size(img, (240, 180))
                preview.save(target_path, format="PNG")
            return True

        if ext == "pdf":
            try:
                import fitz  # type: ignore

                doc = fitz.open(str(source_path))
                try:
                    if len(doc) > 0:
                        page = doc.load_page(0)
                        pix = page.get_pixmap(matrix=fitz.Matrix(0.5, 0.5), alpha=False)
                        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                        preview = _fit_image_to_size(img, (240, 180))
                        preview.save(target_path, format="PNG")
                        return True
                finally:
                    doc.close()
            except Exception as exc:  # noqa: BLE001 - fallback placeholder below
                app.logger.info("Could not render PDF poster thumbnail for %s: %s", source_path, exc)

            canvas = Image.new("RGB", (240, 180), (248, 249, 250))
            draw = ImageDraw.Draw(canvas)
            draw.rectangle((78, 28, 162, 142), fill=(255, 255, 255), outline=(180, 185, 190), width=2)
            draw.rectangle((78, 112, 162, 142), fill=(220, 53, 69))
            draw.text((101, 120), "PDF", fill=(255, 255, 255))
            canvas.save(target_path, format="PNG")
            return True
    except Exception as exc:  # noqa: BLE001 - log and continue without blocking the upload
        app.logger.warning("Could not create poster thumbnail for %s: %s", source_path, exc)
    return False


def ensure_poster_thumbnail_file(order: Order, poster: OrderPosterFile) -> bool:
    if not poster.stored_name:
        return False

    order_folder = Path(app.config["POSTER_UPLOAD_FOLDER"]) / f"order_{order.id}"
    source_path = order_folder / poster.stored_name
    if not source_path.exists():
        return False

    thumb_name = poster.thumb_path
    if not thumb_name:
        safe_stem = Path(secure_filename(poster.original_name or poster.stored_name)).stem or f"poster_{poster.id}"
        thumb_name = f"{poster.id}_{safe_stem}.png"

    thumb_path = order_folder / "thumbnails" / thumb_name
    if thumb_path.exists():
        if poster.thumb_path != thumb_name:
            poster.thumb_path = thumb_name
        return True

    if save_poster_thumbnail(source_path, thumb_path, poster.file_type):
        poster.thumb_path = thumb_name
        return True
    return False


def _normalize_vec(vec):
    length = math.sqrt(vec[0] * vec[0] + vec[1] * vec[1] + vec[2] * vec[2])
    if length <= 0:
        return (0.0, 0.0, 1.0)
    return (vec[0] / length, vec[1] / length, vec[2] / length)


def _calc_normal(v1, v2, v3):
    ax = v2[0] - v1[0]
    ay = v2[1] - v1[1]
    az = v2[2] - v1[2]
    bx = v3[0] - v1[0]
    by = v3[1] - v1[1]
    bz = v3[2] - v1[2]
    return _normalize_vec((ay * bz - az * by, az * bx - ax * bz, ax * by - ay * bx))


def _is_probably_binary_stl(source_path: Path) -> bool:
    try:
        size = source_path.stat().st_size
    except OSError:
        return False
    if size < 84:
        return False
    try:
        with source_path.open("rb") as handle:
            handle.seek(80)
            count_raw = handle.read(4)
            if len(count_raw) != 4:
                return False
            tri_count = struct.unpack("<I", count_raw)[0]
            expected = 84 + tri_count * 50
            return expected == size
    except OSError:
        return False


def _load_binary_stl_triangles(source_path: Path, max_triangles: Optional[int]) -> list:
    triangles = []
    try:
        with source_path.open("rb") as handle:
            handle.seek(80)
            count_raw = handle.read(4)
            if len(count_raw) != 4:
                return []
            tri_count = struct.unpack("<I", count_raw)[0]
            step = 1
            if max_triangles and tri_count > max_triangles:
                step = max(1, tri_count // max_triangles)
            for idx in range(tri_count):
                data = handle.read(50)
                if len(data) < 50:
                    break
                if step > 1 and idx % step != 0:
                    continue
                unpacked = struct.unpack("<12fH", data)
                normal = (unpacked[0], unpacked[1], unpacked[2])
                v1 = (unpacked[3], unpacked[4], unpacked[5])
                v2 = (unpacked[6], unpacked[7], unpacked[8])
                v3 = (unpacked[9], unpacked[10], unpacked[11])
                if normal == (0.0, 0.0, 0.0):
                    normal = _calc_normal(v1, v2, v3)
                triangles.append((normal, (v1, v2, v3)))
    except OSError:
        return []
    return triangles


def _load_ascii_stl_triangles(source_path: Path, max_triangles: Optional[int]) -> list:
    triangles = []
    vertices = []
    try:
        with source_path.open("r", errors="ignore") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                if line.lower().startswith("vertex"):
                    parts = line.split()
                    if len(parts) < 4:
                        continue
                    try:
                        vertex = (float(parts[1]), float(parts[2]), float(parts[3]))
                    except ValueError:
                        continue
                    vertices.append(vertex)
                    if len(vertices) == 3:
                        v1, v2, v3 = vertices
                        vertices = []
                        normal = _calc_normal(v1, v2, v3)
                        triangles.append((normal, (v1, v2, v3)))
                        if max_triangles and len(triangles) >= max_triangles:
                            break
    except OSError:
        return []
    return triangles


def _load_stl_triangles(source_path: Path, max_triangles: Optional[int]) -> list:
    if _is_probably_binary_stl(source_path):
        return _load_binary_stl_triangles(source_path, max_triangles)
    return _load_ascii_stl_triangles(source_path, max_triangles)


def _sample_triangles(triangles: list, max_triangles: Optional[int]) -> list:
    if not max_triangles or len(triangles) <= max_triangles:
        return triangles
    step = max(1, len(triangles) // max_triangles)
    return triangles[::step]


def _render_stl_thumbnail(triangles: list, target_path: Path, size: Tuple[int, int]) -> bool:
    if not triangles:
        return False

    width, height = size
    pad = MODEL_THUMB_PADDING
    pitch = math.radians(35.0)
    yaw = math.radians(45.0)

    cx = math.cos(pitch)
    sx = math.sin(pitch)
    cz = math.cos(yaw)
    sz = math.sin(yaw)

    def rotate(vec):
        x, y, z = vec
        y2 = y * cx - z * sx
        z2 = y * sx + z * cx
        x3 = x * cz - y2 * sz
        y3 = x * sz + y2 * cz
        return (x3, y3, z2)

    rotated = []
    min_x = min_y = min_z = float("inf")
    max_x = max_y = max_z = float("-inf")

    for normal, verts in triangles:
        rv = tuple(rotate(v) for v in verts)
        rn = rotate(normal)
        rotated.append((rn, rv))
        for vx, vy, vz in rv:
            min_x = min(min_x, vx)
            min_y = min(min_y, vy)
            min_z = min(min_z, vz)
            max_x = max(max_x, vx)
            max_y = max(max_y, vy)
            max_z = max(max_z, vz)

    span_x = max_x - min_x
    span_y = max_y - min_y
    if span_x <= 0 or span_y <= 0:
        return False

    scale = min((width - 2 * pad) / span_x, (height - 2 * pad) / span_y)
    scale *= MODEL_THUMB_ZOOM
    if scale <= 0:
        return False

    light_dir = _normalize_vec((0.4, 0.6, 0.7))
    base_color = (80, 140, 200)
    background = (248, 249, 250)

    draw_tris = []
    for normal, verts in rotated:
        pts = []
        center_x = (min_x + max_x) / 2.0
        center_y = (min_y + max_y) / 2.0
        for vx, vy, vz in verts:
            px = (vx - center_x) * scale + (width / 2.0)
            py = (center_y - vy) * scale + (height / 2.0)
            pts.append((px, py))
        depth = sum(v[2] for v in verts) / 3.0
        nrm = _normalize_vec(normal)
        dot = max(0.0, nrm[0] * light_dir[0] + nrm[1] * light_dir[1] + nrm[2] * light_dir[2])
        shade = 0.35 + 0.65 * dot
        color = (int(base_color[0] * shade), int(base_color[1] * shade), int(base_color[2] * shade))
        draw_tris.append((depth, pts, color))

    draw_tris.sort(key=lambda item: item[0])

    image = Image.new("RGB", (width, height), background)
    draw = ImageDraw.Draw(image)
    for _, pts, color in draw_tris:
        draw.polygon(pts, fill=color)

    target_path.parent.mkdir(parents=True, exist_ok=True)
    image.save(target_path, format="PNG")
    return True


def _build_model_thumbnail_names(stored_name: str) -> Tuple[str, str]:
    stem = Path(stored_name).stem or stored_name
    return (f"{stem}_thumb_sm.png", f"{stem}_thumb_lg.png")


def generate_stl_thumbnails(source_path: Path, thumb_sm_path: Path, thumb_lg_path: Path) -> Tuple[bool, bool]:
    try:
        triangles = _load_stl_triangles(source_path, MODEL_THUMB_MAX_TRIANGLES)
        if not triangles:
            return False, False
        small_tris = _sample_triangles(triangles, MODEL_THUMB_SMALL_TRIANGLES)
        large_tris = _sample_triangles(triangles, MODEL_THUMB_LARGE_TRIANGLES)
        small_ok = _render_stl_thumbnail(small_tris, thumb_sm_path, MODEL_THUMB_SMALL_SIZE)
        large_ok = _render_stl_thumbnail(large_tris, thumb_lg_path, MODEL_THUMB_LARGE_SIZE)
        return small_ok, large_ok
    except Exception as exc:  # noqa: BLE001
        app.logger.warning("STL thumbnail generation failed for %s: %s", source_path, exc)
        return False, False


def _fit_image_to_size(image: Image.Image, size: Tuple[int, int]) -> Image.Image:
    background = (248, 249, 250)
    canvas = Image.new("RGB", size, background)
    img = image.convert("RGB")
    img.thumbnail(size, Image.LANCZOS)
    offset = ((size[0] - img.width) // 2, (size[1] - img.height) // 2)
    canvas.paste(img, offset)
    return canvas


def _image_from_data_url(data_url: str) -> Optional[Image.Image]:
    if not data_url or not data_url.startswith("data:image/"):
        return None
    try:
        header, encoded = data_url.split(",", 1)
    except ValueError:
        return None
    if ";base64" not in header:
        return None
    try:
        raw = base64.b64decode(encoded)
    except (ValueError, binascii.Error):
        return None
    try:
        return Image.open(BytesIO(raw))
    except Exception:
        return None


def save_model_thumbnail_from_image(image: Image.Image, thumb_sm_path: Path, thumb_lg_path: Path) -> Tuple[bool, bool]:
    thumb_sm_path.parent.mkdir(parents=True, exist_ok=True)
    small_ok = False
    large_ok = False
    try:
        large = _fit_image_to_size(image, MODEL_THUMB_LARGE_SIZE)
        large.save(thumb_lg_path, format="PNG")
        large_ok = True
        small = _fit_image_to_size(image, MODEL_THUMB_SMALL_SIZE)
        small.save(thumb_sm_path, format="PNG")
        small_ok = True
    except Exception as exc:  # noqa: BLE001
        app.logger.warning("Could not save uploaded model thumbnails: %s", exc)
    return small_ok, large_ok


def update_order_file_preview(order_file: OrderFile, source_path: Path) -> None:
    file_type = (order_file.file_type or "").lower()
    if file_type not in {"stl", "3mf"}:
        order_file.has_3d_preview = False
        order_file.preview_status = "unsupported"
        return

    if not source_path.exists():
        order_file.has_3d_preview = False
        order_file.preview_status = "missing"
        return

    order_file.has_3d_preview = True

    thumb_sm_name, thumb_lg_name = _build_model_thumbnail_names(order_file.stored_name)
    thumb_folder = source_path.parent / "thumbnails"
    thumb_sm_path = thumb_folder / thumb_sm_name
    thumb_lg_path = thumb_folder / thumb_lg_name

    small_ok = thumb_sm_path.exists()
    large_ok = thumb_lg_path.exists()
    if file_type == "stl" and (not small_ok or not large_ok):
        gen_small, gen_large = generate_stl_thumbnails(source_path, thumb_sm_path, thumb_lg_path)
        small_ok = small_ok or gen_small
        large_ok = large_ok or gen_large

    order_file.thumb_sm_path = thumb_sm_name if small_ok else None
    order_file.thumb_lg_path = thumb_lg_name if large_ok else None
    if file_type == "3mf":
        order_file.preview_status = "ok"
    else:
        order_file.preview_status = "ok" if (small_ok or large_ok) else "failed"


def _parse_float_token(raw_value: str | None) -> float | None:
    if not raw_value:
        return None
    normalized = raw_value.strip().replace(",", ".")
    try:
        return float(normalized)
    except ValueError:
        return None


def _parse_gcode_duration_minutes(raw_value: str | None) -> int | None:
    if not raw_value:
        return None
    value = raw_value.strip().lower()
    total_minutes = 0.0

    for pattern, factor in (
        (r"(\d+(?:[.,]\d+)?)\s*(?:d|day|days)\b", 1440),
        (r"(\d+(?:[.,]\d+)?)\s*(?:h|hr|hrs|hour|hours)\b", 60),
        (r"(\d+(?:[.,]\d+)?)\s*(?:m|min|mins|minute|minutes)\b", 1),
        (r"(\d+(?:[.,]\d+)?)\s*(?:s|sec|secs|second|seconds)\b", 1 / 60),
    ):
        match = re.search(pattern, value)
        if match:
            total_minutes += (_parse_float_token(match.group(1)) or 0.0) * factor

    if total_minutes:
        return max(0, int(round(total_minutes)))

    colon_match = re.search(r"\b(\d{1,3}):(\d{2})(?::(\d{2}))?\b", value)
    if colon_match:
        first = int(colon_match.group(1))
        second = int(colon_match.group(2))
        third = int(colon_match.group(3) or 0)
        total_minutes = first * 60 + second + (third / 60 if colon_match.group(3) else 0)
        return max(0, int(round(total_minutes)))

    numeric = _parse_float_token(value)
    if numeric is not None:
        return max(0, int(round(numeric / 60)))
    return None


GCODE_METADATA_SCAN_BYTES = 2 * 1024 * 1024


def _read_gcode_metadata_lines(path: Path) -> list[str]:
    """Read only the G-code regions where slicers normally store metadata."""
    with path.open("rb") as handle:
        head = handle.read(GCODE_METADATA_SCAN_BYTES)
        file_size = handle.seek(0, os.SEEK_END)

        tail = b""
        if file_size > GCODE_METADATA_SCAN_BYTES:
            handle.seek(max(GCODE_METADATA_SCAN_BYTES, file_size - GCODE_METADATA_SCAN_BYTES))
            tail = handle.read(GCODE_METADATA_SCAN_BYTES)

    content = head if not tail else head + b"\n" + tail
    return content.decode("utf-8", errors="ignore").splitlines()


def extract_gcode_metadata(path: Path) -> dict[str, float | int]:
    metadata: dict[str, float | int] = {}
    try:
        for raw_line in _read_gcode_metadata_lines(path):
            line = raw_line.strip()
            lower = line.lower()

            if "duration_min" not in metadata:
                time_match = re.search(r";\s*time\s*:\s*(\d+(?:[.,]\d+)?)\s*$", lower)
                if time_match:
                    seconds = _parse_float_token(time_match.group(1))
                    if seconds is not None:
                        metadata["duration_min"] = max(0, int(round(seconds / 60)))

            if "duration_min" not in metadata and any(
                token in lower for token in ("estimated printing time", "estimated print time", "print time", "printing time")
            ):
                duration = _parse_gcode_duration_minutes(line)
                if duration is not None:
                    metadata["duration_min"] = duration

            if "filament_m" not in metadata:
                filament_bracket_m_match = re.search(r"filament\s+used\s*\[(mm|m)\]\s*=\s*(\d+(?:[.,]\d+)?)", lower)
                if filament_bracket_m_match:
                    value = _parse_float_token(filament_bracket_m_match.group(2))
                    if value is not None:
                        metadata["filament_m"] = value / 1000 if filament_bracket_m_match.group(1) == "mm" else value

            if "filament_m" not in metadata:
                filament_m_match = re.search(r"filament\s+used.*?(\d+(?:[.,]\d+)?)\s*m\b", lower)
                if filament_m_match:
                    value = _parse_float_token(filament_m_match.group(1))
                    if value is not None:
                        metadata["filament_m"] = value

            if "filament_m" not in metadata:
                filament_mm_match = re.search(r"filament\s+used.*?(\d+(?:[.,]\d+)?)\s*mm\b", lower)
                if filament_mm_match:
                    value = _parse_float_token(filament_mm_match.group(1))
                    if value is not None:
                        metadata["filament_m"] = value / 1000

            if "filament_g" not in metadata:
                filament_bracket_g_match = re.search(
                    r"(?:filament\s+used|total\s+filament\s+used)\s*\[g\]\s*=\s*(\d+(?:[.,]\d+)?)",
                    lower,
                )
                if filament_bracket_g_match:
                    value = _parse_float_token(filament_bracket_g_match.group(1))
                    if value is not None:
                        metadata["filament_g"] = value

            if "filament_g" not in metadata:
                filament_g_match = re.search(
                    r"(?:filament\s+used|filament\s+weight|total\s+filament).*?(\d+(?:[.,]\d+)?)\s*g\b",
                    lower,
                )
                if filament_g_match:
                    value = _parse_float_token(filament_g_match.group(1))
                    if value is not None:
                        metadata["filament_g"] = value

            if len(metadata) == 3:
                break
    except OSError:
        return metadata

    return metadata


def apply_gcode_metadata_to_job(job: OrderPrintJob, path: Path) -> bool:
    if job.duration_min is not None and job.filament_m is not None and job.filament_g is not None:
        return False

    metadata = extract_gcode_metadata(path)
    changed = False
    if job.duration_min is None and "duration_min" in metadata:
        job.duration_min = int(metadata["duration_min"])
        changed = True
    if job.filament_m is None and "filament_m" in metadata:
        job.filament_m = round(float(metadata["filament_m"]), 2)
        changed = True
    if job.filament_g is None and "filament_g" in metadata:
        job.filament_g = round(float(metadata["filament_g"]), 2)
        changed = True
    return changed


def current_print_start_time() -> datetime:
    return datetime.utcnow().replace(second=0, microsecond=0)


# ============================================================
# Blueprints
# ============================================================

admin_bp = create_admin_blueprint(lambda: inject_globals().get("t"))
app.register_blueprint(admin_bp)


@app.template_filter("nl2br")
def nl2br_filter(s: str):
    """
    Filter f├╝r Jinja: wandelt Zeilenumbr├╝che in <br> um und escaped den Text zuvor.
    Eignet sich f├╝r Chat-/Text-Ausgabe.
    """
    if not s:
        return ""
    return Markup("<br>".join(escape(s).splitlines()))


# ============================================================
# Login- / Rollen-Setup
# ============================================================

login_manager = LoginManager(app)
login_manager.login_view = "login"  # wohin bei @login_required ohne Login?


# ============================================================
# Datenbank-Modelle (ausgelagert in models.py)
# ============================================================
# ============================================================
# Login-Backend
# ============================================================

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


# ============================================================
# CLI-Kommandos (Datenbank & Stammdaten)
# ============================================================

@app.cli.command("init-db")
def init_db():
    """Initialisiert die Datenbank (einmalig ausf├╝hren)."""
    db.create_all()
    print("Datenbank initialisiert.")


@app.cli.command("create-admin")
def create_admin():
    """Erstellt einen Admin-User (interaktiv)."""
    email = input("Admin email: ").strip().lower()
    password = input("Admin password: ").strip()

    if User.query.filter_by(email=email).first():
        print("Error: User with this email already exists.")
        return

    user = User(email=email, role="admin")
    user.set_password(password)
    db.session.add(user)
    db.session.commit()
    print(f"Admin user '{email}' created.")


@app.cli.command("init-stammdaten")
def init_stammdaten():
    """
    Legt einige Standard-Materialien und -Farben an, falls sie noch nicht existieren.
    Beispielaufruf:
        flask --app app init-stammdaten
    """
    base_materials = ["PLA", "ABS", "PETG", "TPU"]
    for name in base_materials:
        if not Material.query.filter_by(name=name).first():
            db.session.add(Material(name=name))
            print(f"Material angelegt: {name}")

    base_colors = [
        ("Schwarz", "#000000"),
        ("Wei├ƒ", "#FFFFFF"),
        ("Rot", "#FF0000"),
        ("Gelb", "#FFFF00"),
        ("Blau", "#0000FF"),
        ("Grau", "#808080"),
    ]
    for name, hex_code in base_colors:
        if not Color.query.filter_by(name=name).first():
            db.session.add(Color(name=name, hex_code=hex_code))
            print(f"Farbe angelegt: {name} ({hex_code})")

    db.session.commit()
    print("Stammdaten initialisiert.")


@app.cli.command("version")
def show_version():
    """Zeigt die aktuelle NeoFab-Version an."""
    print(f"NeoFab version: {APP_VERSION}")


# ============================================================
# Routen: Landing / Auth
# ============================================================

@app.route("/")
def landing():
    """Einfache Landingpage vor dem Login."""
    return render_template("landing.html")


@app.route("/impressum")
def imprint():
    settings = load_app_settings(app)
    imprint_md = settings.get("imprint_markdown") or ""
    imprint_html = render_legal_markdown(imprint_md)
    return render_template(
        "impressum.html",
        imprint_html=imprint_html,
        has_imprint=bool(imprint_md.strip()),
    )


@app.route("/datenschutz")
def privacy():
    settings = load_app_settings(app)
    privacy_md = settings.get("privacy_markdown") or ""
    privacy_html = render_legal_markdown(privacy_md)
    return render_template(
        "datenschutz.html",
        privacy_html=privacy_html,
        has_privacy=bool(privacy_md.strip()),
    )


@app.route("/info")
def info():
    return render_template("info.html")


def _activation_token_hash(token: str) -> str:
    return hashlib.sha256((token or "").encode("utf-8")).hexdigest()


def _activation_valid_minutes(settings: dict) -> int:
    return coerce_positive_int(
        settings.get("activation_token_valid_minutes"),
        DEFAULT_SETTINGS["activation_token_valid_minutes"],
    )


def create_user_activation_token(user: User, source: str = "user_activation") -> tuple[str, datetime]:
    settings = load_app_settings(app)
    valid_minutes = _activation_valid_minutes(settings)
    now = datetime.utcnow()
    token = secrets.token_urlsafe(32)

    UserActivationToken.query.filter_by(user_id=user.id, used_at=None).update(
        {"used_at": now},
        synchronize_session=False,
    )
    activation = UserActivationToken(
        user_id=user.id,
        token_hash=_activation_token_hash(token),
        source=source,
        expires_at=now + timedelta(minutes=valid_minutes),
        created_at=now,
    )
    db.session.add(activation)
    return token, activation.expires_at


def send_activation_link_for_user(user: User, source: str = "user_activation") -> bool:
    token, expires_at = create_user_activation_token(user, source=source)
    db.session.flush()
    activation_url = url_for("activate_user", token=token, _external=True)
    sent = send_user_activation_notification(
        app,
        user,
        activation_url=activation_url,
        expires_at=expires_at,
        source=source,
    )
    write_audit_log(
        app,
        "user_activation_token_created",
        user=current_user if current_user.is_authenticated else user,
        details={
            "target_user_id": user.id,
            "target_email": user.email,
            "source": source,
            "expires_at": expires_at.isoformat(),
            "email_sent": sent,
        },
    )
    return sent


def create_password_reset_token(user: User) -> tuple[str, datetime]:
    settings = load_app_settings(app)
    valid_minutes = _activation_valid_minutes(settings)
    now = datetime.utcnow()
    token = secrets.token_urlsafe(32)

    UserPasswordResetToken.query.filter_by(user_id=user.id, used_at=None).update(
        {"used_at": now},
        synchronize_session=False,
    )
    reset_token = UserPasswordResetToken(
        user_id=user.id,
        token_hash=_activation_token_hash(token),
        expires_at=now + timedelta(minutes=valid_minutes),
        created_at=now,
    )
    db.session.add(reset_token)
    return token, reset_token.expires_at


def send_password_reset_link_for_user(user: User) -> bool:
    token, expires_at = create_password_reset_token(user)
    db.session.flush()
    reset_url = url_for("password_reset_confirm", token=token, _external=True)
    sent = send_password_reset_notification(
        app,
        user,
        reset_url=reset_url,
        expires_at=expires_at,
    )
    write_audit_log(
        app,
        "password_reset_token_created",
        user=user,
        details={
            "target_user_id": user.id,
            "target_email": user.email,
            "expires_at": expires_at.isoformat(),
            "email_sent": sent,
        },
    )
    return sent


@app.route("/activate/<token>")
def activate_user(token):
    trans = inject_globals().get("t")
    activation = UserActivationToken.query.filter_by(
        token_hash=_activation_token_hash(token)
    ).first()
    now = datetime.utcnow()

    if not activation:
        flash(trans("flash_activation_invalid"), "danger")
        return redirect(url_for("login"))
    if activation.used_at is not None:
        flash(trans("flash_activation_used"), "warning")
        return redirect(url_for("login"))
    if activation.expires_at < now:
        flash(trans("flash_activation_expired"), "warning")
        return redirect(url_for("login"))

    user = User.query.get(activation.user_id)
    if not user or user.deleted_at is not None:
        activation.used_at = now
        db.session.commit()
        flash(trans("flash_activation_invalid"), "danger")
        return redirect(url_for("login"))

    user.is_active = True
    activation.used_at = now
    db.session.commit()
    write_audit_log(
        app,
        "user_activated",
        user=user,
        details={
            "target_user_id": user.id,
            "target_email": user.email,
            "source": activation.source or "activation_link",
        },
    )
    send_user_welcome_notification(app, user, source="activation")
    flash(trans("flash_activation_success"), "success")
    return redirect(url_for("login"))


@app.route("/password-reset", methods=["GET", "POST"])
def password_reset_request():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))

    trans = inject_globals().get("t")
    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        if not email:
            flash(trans("flash_email_required"), "warning")
            return render_template("password_reset_request.html")

        user = User.query.filter_by(email=email).first()
        sent = False
        if user and user.deleted_at is None and user.is_active:
            sent = send_password_reset_link_for_user(user)
            db.session.commit()

        write_audit_log(
            app,
            "password_reset_requested",
            user=user if user else None,
            details={
                "email": email,
                "matched_user": bool(user),
                "eligible": bool(user and user.deleted_at is None and user.is_active),
                "email_sent": sent,
            },
        )
        flash(trans("flash_password_reset_request_received"), "info")
        return redirect(url_for("login"))

    return render_template("password_reset_request.html")


@app.route("/password-reset/<token>", methods=["GET", "POST"])
def password_reset_confirm(token):
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))

    trans = inject_globals().get("t")
    reset_token = UserPasswordResetToken.query.filter_by(
        token_hash=_activation_token_hash(token)
    ).first()
    now = datetime.utcnow()

    if not reset_token:
        flash(trans("flash_password_reset_invalid"), "danger")
        return redirect(url_for("login"))
    if reset_token.used_at is not None:
        flash(trans("flash_password_reset_used"), "warning")
        return redirect(url_for("login"))
    if reset_token.expires_at < now:
        flash(trans("flash_password_reset_expired"), "warning")
        return redirect(url_for("password_reset_request"))

    user = User.query.get(reset_token.user_id)
    if not user or user.deleted_at is not None or not user.is_active:
        reset_token.used_at = now
        db.session.commit()
        flash(trans("flash_password_reset_invalid"), "danger")
        return redirect(url_for("login"))

    if request.method == "POST":
        password = request.form.get("password", "")
        password2 = request.form.get("password2", "")
        if not password:
            flash(trans("flash_password_required"), "warning")
            return render_template("password_reset_confirm.html", token=token)
        if password != password2:
            flash(trans("flash_passwords_mismatch"), "warning")
            return render_template("password_reset_confirm.html", token=token)

        user.set_password(password)
        reset_token.used_at = now
        db.session.commit()
        write_audit_log(
            app,
            "password_reset_completed",
            user=user,
            details={"target_user_id": user.id, "target_email": user.email},
        )
        flash(trans("flash_password_reset_success"), "success")
        return redirect(url_for("login"))

    return render_template("password_reset_confirm.html", token=token)


@app.route("/login", methods=["GET", "POST"])
def login():
    """Login-Formular & Login-Logik."""
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        trans = inject_globals().get("t")
        action = (request.form.get("action") or "").strip()
        if not action and (
            "announcement_id" in request.form
            or "announcement_title" in request.form
            or "announcement_body" in request.form
            or "announcement_priority" in request.form
        ):
            action = "update_announcement"
        allowed_priorities = set(ANNOUNCEMENT_PRIORITY_META.keys())

        if action == "update_announcement":
            if current_user.role != "admin":
                abort(403)
            try:
                announcement_id = int(request.form.get("announcement_id", "0"))
            except ValueError:
                announcement_id = 0

            if not announcement_id:
                flash(trans("flash_announcement_not_found"), "warning")
                return redirect(url_for("profile"))

            announcement = Announcement.query.filter_by(id=announcement_id).first()
            if not announcement:
                flash(trans("flash_announcement_not_found"), "warning")
                return redirect(url_for("profile"))

            title = (request.form.get("announcement_title") or "").strip()
            body = (request.form.get("announcement_body") or "").strip()
            priority = (request.form.get("announcement_priority") or "info").strip()
            if priority not in allowed_priorities:
                priority = "info"
            if not title or not body:
                flash(trans("flash_announcement_required"), "warning")
                return redirect(url_for("profile"))

            announcement.title = title[:200]
            announcement.body = body
            announcement.priority = priority
            announcement.updated_by_id = current_user.id
            announcement.updated_at = datetime.utcnow()
            AnnouncementRead.query.filter_by(announcement_id=announcement.id).delete()
            db.session.commit()
            flash(trans("flash_announcement_updated"), "success")
            return redirect(url_for("profile"))
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        user = User.query.filter_by(email=email).first()
        if user and user.check_password(password):
            if user.deleted_at is not None:
                flash(trans("flash_account_deleted"), "danger")
                return render_template("login.html")
            if not user.is_active:
                flash(trans("flash_account_inactive"), "warning")
                return render_template("login.html")

            timing_start = perf_counter()
            timing_marks = {}

            login_user(user)
            timing_marks["login_user_ms"] = round((perf_counter() - timing_start) * 1000, 1)

            step_start = perf_counter()
            write_audit_log(app, "user_login", user=user)
            timing_marks["audit_log_ms"] = round((perf_counter() - step_start) * 1000, 1)

            step_start = perf_counter()
            load_app_settings(app)
            timing_marks["settings_ms"] = round((perf_counter() - step_start) * 1000, 1)

            session.permanent = True
            session[SESSION_LAST_ACTIVE_KEY] = datetime.utcnow().isoformat()
            user.last_login_at = datetime.utcnow()

            step_start = perf_counter()
            db.session.commit()
            timing_marks["db_commit_ms"] = round((perf_counter() - step_start) * 1000, 1)
            timing_marks["total_ms"] = round((perf_counter() - timing_start) * 1000, 1)

            if timing_marks["total_ms"] >= 750 or timing_marks["audit_log_ms"] >= 250 or timing_marks["db_commit_ms"] >= 250:
                app.logger.warning(
                    "Slow login for user_id=%s email=%s timings=%s",
                    user.id,
                    user.email,
                    timing_marks,
                )
                write_audit_log(
                    app,
                    "login_timing_slow",
                    user=user,
                    level="warning",
                    details=timing_marks,
                )

            flash(trans("flash_login_success"), "success")
            next_page = request.args.get("next")
            return redirect(next_page or url_for("dashboard"))
        else:
            flash(trans("flash_invalid_credentials"), "danger")

    return render_template("login.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    """Registrierungs-Formular & Account-Anlage f├╝r neue Nutzer."""
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))

    settings = load_app_settings(app)
    registration_domain_check_enabled = bool(settings.get("registration_domain_check_enabled"))
    registration_allowed_domains = normalize_registration_domains(settings.get("registration_allowed_domains", ""))

    if request.method == "POST":
        trans = inject_globals().get("t")
        action = (request.form.get("action") or "").strip()
        allowed_priorities = set(ANNOUNCEMENT_PRIORITY_META.keys())

        if action == "update_announcement":
            if current_user.role != "admin":
                abort(403)
            try:
                announcement_id = int(request.form.get("announcement_id", "0"))
            except ValueError:
                announcement_id = 0

            if not announcement_id:
                flash(trans("flash_announcement_not_found"), "warning")
                return redirect(url_for("profile"))

            announcement = Announcement.query.filter_by(id=announcement_id).first()
            if not announcement:
                flash(trans("flash_announcement_not_found"), "warning")
                return redirect(url_for("profile"))

            title = (request.form.get("announcement_title") or "").strip()
            body = (request.form.get("announcement_body") or "").strip()
            priority = (request.form.get("announcement_priority") or "info").strip()
            if priority not in allowed_priorities:
                priority = "info"
            if not title or not body:
                flash(trans("flash_announcement_required"), "warning")
                return redirect(url_for("profile"))

            announcement.title = title[:200]
            announcement.body = body
            announcement.priority = priority
            announcement.updated_by_id = current_user.id
            announcement.updated_at = datetime.utcnow()
            AnnouncementRead.query.filter_by(announcement_id=announcement.id).delete()
            db.session.commit()
            flash(trans("flash_announcement_updated"), "success")
            return redirect(url_for("profile"))
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        password2 = request.form.get("password2", "")
        language = (request.form.get("language") or "").strip().lower() or DEFAULT_LANG
        if language not in SUPPORTED_LANGS:
            language = DEFAULT_LANG
        salutation = request.form.get("salutation", "").strip()
        allowed_salutations = set(REGISTRATION_SALUTATION_OPTIONS.get(language, []))
        if salutation and salutation not in allowed_salutations:
            salutation = ""
        first_name = request.form.get("first_name", "").strip()
        last_name = request.form.get("last_name", "").strip()

        # Validierung
        email_domain = email.rsplit("@", 1)[-1].lower() if "@" in email else ""
        domain_blocked = (
            registration_domain_check_enabled
            and not is_registration_domain_allowed(email_domain, registration_allowed_domains)
        )

        if not email or not password or not salutation or not first_name or not last_name:
            write_audit_log(
                app,
                "registration_rejected",
                level="warning",
                details={
                    "reason": "required_fields_missing",
                    "email": email,
                    "language": language,
                    "has_password": bool(password),
                    "has_salutation": bool(salutation),
                    "has_first_name": bool(first_name),
                    "has_last_name": bool(last_name),
                },
            )
            flash(trans("flash_required_fields"), "danger")
        elif password != password2:
            write_audit_log(
                app,
                "registration_rejected",
                level="warning",
                details={"reason": "password_mismatch", "email": email},
            )
            flash(trans("flash_passwords_mismatch"), "danger")
        elif domain_blocked:
            write_audit_log(
                app,
                "registration_rejected",
                level="warning",
                details={
                    "reason": "domain_not_allowed",
                    "email": email,
                    "email_domain": email_domain,
                    "allowed_domains": registration_allowed_domains,
                    "registration_domain_check_enabled": registration_domain_check_enabled,
                },
            )
            flash(
                trans("flash_registration_domain_not_allowed").format(
                    domains="; ".join(registration_allowed_domains)
                ),
                "danger",
            )
        elif User.query.filter_by(email=email).first():
            write_audit_log(
                app,
                "registration_rejected",
                level="warning",
                details={"reason": "email_already_registered", "email": email},
            )
            flash(trans("flash_email_registered"), "warning")
        else:
            account_activation_required = bool(settings.get("account_activation_required", True))
            user = User(
                email=email,
                role="user",
                language=language,
                is_active=not account_activation_required,
                salutation=salutation,
                first_name=first_name,
                last_name=last_name,
                address=request.form.get("address") or None,
                position=request.form.get("position") or None,
                cost_center=request.form.get("cost_center") or None,
                study_program=request.form.get("study_program") or None,
                note=request.form.get("note") or None,
            )
            user.set_password(password)
            db.session.add(user)
            db.session.flush()
            activation_sent = False
            if account_activation_required:
                activation_sent = send_activation_link_for_user(user, source="registration")
            db.session.commit()
            write_audit_log(
                app,
                "user_created",
                user=user,
                details={
                    "target_user_id": user.id,
                    "target_email": user.email,
                    "target_role": user.role,
                    "target_language": user.language,
                    "source": "registration",
                    "activation_required": account_activation_required,
                    "activation_email_sent": activation_sent,
                },
            )
            if account_activation_required and activation_sent:
                flash(trans("flash_registration_activation_email_sent"), "success")
            elif account_activation_required:
                flash(trans("flash_registration_activation_email_failed"), "warning")
            else:
                send_user_welcome_notification(app, user, source="registration")
                flash(trans("flash_registration_success"), "success")
            return redirect(url_for("login"))

    register_form = {
        "email": (request.form.get("email") or "").strip() if request.method == "POST" else "",
        "language": (request.form.get("language") or "").strip().lower() if request.method == "POST" else DEFAULT_LANG,
        "salutation": (request.form.get("salutation") or "").strip() if request.method == "POST" else "",
        "first_name": (request.form.get("first_name") or "").strip() if request.method == "POST" else "",
        "last_name": (request.form.get("last_name") or "").strip() if request.method == "POST" else "",
        "address": (request.form.get("address") or "").strip() if request.method == "POST" else "",
        "position": (request.form.get("position") or "").strip() if request.method == "POST" else "",
        "cost_center": (request.form.get("cost_center") or "").strip() if request.method == "POST" else "",
        "study_program": (request.form.get("study_program") or "").strip() if request.method == "POST" else "",
        "note": (request.form.get("note") or "").strip() if request.method == "POST" else "",
    }
    if register_form["language"] not in SUPPORTED_LANGS:
        register_form["language"] = DEFAULT_LANG

    return render_template(
        "register.html",
        registration_domain_check_enabled=registration_domain_check_enabled,
        registration_allowed_domains_display="; ".join(registration_allowed_domains),
        registration_language_options=REGISTRATION_LANGUAGE_OPTIONS,
        registration_salutation_options=REGISTRATION_SALUTATION_OPTIONS,
        register_form=register_form,
    )


# ============================================================
# Routen: Profil
# ============================================================


@app.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    """
    Profilseite fuer eingeloggte User, um eigene Stammdaten zu pflegen.
    """
    user = User.query.get_or_404(current_user.id)
    dashboard_areas = OrderArea.query.order_by(OrderArea.name.asc()).all()
    dashboard_area_ids = {area.id for area in dashboard_areas}

    if request.method == "POST":
        trans = inject_globals().get("t")
        action = request.form.get("action", "update_profile")
        if action == "delete_email_favorite":
            try:
                favorite_id = int(request.form.get("favorite_id", "0"))
            except ValueError:
                favorite_id = 0
            favorite = UserEmailFavorite.query.filter_by(
                id=favorite_id,
                user_id=user.id,
            ).first()
            if favorite:
                db.session.delete(favorite)
                db.session.commit()
                flash(trans("flash_profile_email_favorite_deleted"), "info")
            else:
                flash(trans("flash_profile_email_favorite_not_found"), "warning")
            return redirect(url_for("profile"))

        email = request.form.get("email", "").strip().lower()

        salutation = request.form.get("salutation") or None
        first_name = request.form.get("first_name") or None
        last_name = request.form.get("last_name") or None
        address = request.form.get("address") or None
        position = request.form.get("position") or None
        cost_center = request.form.get("cost_center") or None
        study_program = request.form.get("study_program") or None
        note = request.form.get("note") or None

        new_password = request.form.get("password", "")
        new_password2 = request.form.get("password2", "")
        language = request.form.get("language", "").strip().lower() or "en"
        if language not in SUPPORTED_LANGS:
            language = "en"
        theme_mode = request.form.get("theme_mode", "").strip().lower() or "light"
        if theme_mode not in {"light", "dark"}:
            theme_mode = "light"
        status_email_enabled = bool(request.form.get("status_email_enabled"))

        # Basisvalidierungen
        if not email:
            flash(trans("flash_email_required"), "danger")
        else:
            existing = User.query.filter_by(email=email).first()
            if existing and existing.id != user.id:
                flash(trans("flash_user_email_exists"), "danger")
            elif new_password and new_password != new_password2:
                flash(trans("flash_passwords_mismatch"), "danger")
            else:
                user.email = email
                user.salutation = salutation
                user.first_name = first_name
                user.last_name = last_name
                user.address = address
                user.position = position
                user.cost_center = cost_center
                user.study_program = study_program
                user.note = note
                user.language = language
                user.theme_mode = theme_mode
                user.status_email_enabled = status_email_enabled

                if new_password:
                    user.set_password(new_password)

                if user.role == "worker":
                    selected_ids = set()
                    for raw_id in request.form.getlist("worker_category_ids"):
                        try:
                            selected_ids.add(int(raw_id))
                        except (TypeError, ValueError):
                            continue
                    valid_categories = OrderCategory.query.filter(
                        OrderCategory.active.is_(True),
                        OrderCategory.id.in_(selected_ids) if selected_ids else False,
                    ).all()
                    valid_ids = {category.id for category in valid_categories}
                    existing_permissions = UserOrderCategoryPermission.query.filter_by(
                        user_id=user.id,
                    ).all()
                    existing_by_category = {
                        permission.category_id: permission
                        for permission in existing_permissions
                    }
                    for permission in existing_permissions:
                        if permission.category_id not in valid_ids:
                            db.session.delete(permission)
                    for category_id in valid_ids:
                        permission = existing_by_category.get(category_id)
                        if permission:
                            permission.can_manage = True
                        else:
                            db.session.add(
                                UserOrderCategoryPermission(
                                    user_id=user.id,
                                    category_id=category_id,
                                    can_manage=True,
                                )
                            )
                else:
                    UserOrderCategoryPermission.query.filter_by(user_id=user.id).delete()

                if user.role in {"admin", "worker"}:
                    selected_area_ids = set()
                    for raw_id in request.form.getlist("dashboard_area_ids"):
                        try:
                            selected_area_ids.add(int(raw_id))
                        except (TypeError, ValueError):
                            continue
                    valid_area_ids = {area_id for area_id in selected_area_ids if area_id in dashboard_area_ids}
                    UserOrderAreaPreference.query.filter_by(user_id=user.id).delete()
                    for area_id in sorted(valid_area_ids):
                        db.session.add(
                            UserOrderAreaPreference(
                                user_id=user.id,
                                area_id=area_id,
                            )
                        )
                else:
                    UserOrderAreaPreference.query.filter_by(user_id=user.id).delete()

                db.session.commit()
                flash(trans("flash_profile_updated"), "success")
                return redirect(url_for("profile"))

    announcements = Announcement.query.order_by(Announcement.created_at.desc()).all()
    announcement_reads = AnnouncementRead.query.filter_by(user_id=current_user.id).all()
    read_by_announcement = {entry.announcement_id: entry for entry in announcement_reads}
    announcements_read = [a for a in announcements if a.id in read_by_announcement]
    worker_categories = OrderCategory.query.filter_by(active=True).order_by(OrderCategory.name.asc()).all()
    selected_worker_category_ids = {
        permission.category_id
        for permission in UserOrderCategoryPermission.query.filter_by(
            user_id=user.id,
            can_manage=True,
        ).all()
    }
    selected_dashboard_area_ids = {
        preference.area_id
        for preference in UserOrderAreaPreference.query.filter_by(user_id=user.id).all()
    }
    email_favorites = (
        UserEmailFavorite.query
        .filter_by(user_id=user.id)
        .order_by(UserEmailFavorite.email.asc())
        .all()
    )

    return render_template(
        "profile.html",
        user=user,
        worker_categories=worker_categories,
        selected_worker_category_ids=selected_worker_category_ids,
        dashboard_areas=dashboard_areas,
        selected_dashboard_area_ids=selected_dashboard_area_ids,
        email_favorites=email_favorites,
        announcements_read=announcements_read,
        announcement_priority_meta=ANNOUNCEMENT_PRIORITY_META,
        announcement_form_token=_new_announcement_form_token() if current_user.role == "admin" else "",
    )


# ============================================================
# Routen: Tutorials
# ============================================================


def extract_youtube_id(url: str) -> str | None:
    """
    Extracts the YouTube video ID from typical watch/embed/shorts URLs.
    Supports youtube.com, youtube-nocookie.com, youtu.be and m.youtube.com.
    """
    if not url:
        return None
    candidate = url if "://" in url else f"https://{url}"
    try:
        parsed = urlparse(candidate)
    except Exception:
        return None

    host = (parsed.hostname or "").lower()
    video_id = None

    # Direct host-based parsing
    if host.endswith("youtu.be"):
        parts = [p for p in parsed.path.split("/") if p]
        video_id = parts[0] if parts else None
    else:
        qs = parse_qs(parsed.query)
        video_id = qs.get("v", [None])[0]
        if not video_id:
            parts = [p for p in parsed.path.split("/") if p]
            if len(parts) >= 2 and parts[0] in {"embed", "shorts"}:
                video_id = parts[1]

    # Regex fallback to catch uncommon formats
    if not video_id:
        match = re.search(r"(?:v=|\/)([0-9A-Za-z_-]{11})(?:[&?#]|$)", url)
        if match:
            video_id = match.group(1)

    return video_id


@app.route("/tutorials")
@login_required
def tutorials():
    """
    Zeigt verfuegbare Trainingsvideos fuer Anwender.
    """
    ensure_training_playlist_schema()
    videos = TrainingVideo.query.order_by(TrainingVideo.sort_order.asc(), TrainingVideo.created_at.desc()).all()
    playlists = TrainingPlaylist.query.order_by(TrainingPlaylist.title.asc()).all()
    playlist_lookup = {playlist.id: playlist for playlist in playlists}

    def build_video_entry(video: TrainingVideo) -> dict:
        pdf_url = None
        pdf_name = None
        has_pdf = False
        if video.pdf_filename:
            pdf_path = Path(app.config["TRAINING_UPLOAD_FOLDER"]) / video.pdf_filename
            if pdf_path.exists():
                pdf_url = url_for("tutorial_pdf", video_id=video.id)
                pdf_name = video.pdf_original_name or video.pdf_filename
                has_pdf = True

        youtube_url = (video.youtube_url or "").strip()
        embed_url = ""
        thumb_url = None
        has_video = False
        if youtube_url:
            vid = extract_youtube_id(youtube_url)
            embed_url = (
                f"https://www.youtube-nocookie.com/embed/{vid}"
                if vid
                else youtube_url
            )
            thumb_url = f"https://img.youtube.com/vi/{vid}/hqdefault.jpg" if vid else None
            has_video = True

        return {
            "video": video,
            "embed_url": embed_url,
            "thumb_url": thumb_url,
            "has_pdf": has_pdf,
            "has_video": has_video,
            "pdf_url": pdf_url,
            "pdf_name": pdf_name,
        }

    grouped = {}
    for video in videos:
        playlist = playlist_lookup.get(video.playlist_id)
        key = playlist.id if playlist else None
        if key not in grouped:
            grouped[key] = {
                "playlist": playlist,
                "entries": [],
            }
        grouped[key]["entries"].append(build_video_entry(video))

    ordered_keys = [p.id for p in playlists if p.id in grouped]
    if None in grouped:
        ordered_keys.append(None)

    video_groups = []
    for key in ordered_keys:
        playlist = grouped[key]["playlist"]
        video_groups.append(
            {
                "title": playlist.title if playlist else None,
                "description": playlist.short_description if playlist else None,
                "is_ungrouped": playlist is None,
                "entries": grouped[key]["entries"],
            }
        )

    return render_template("tutorials.html", video_groups=video_groups)


@app.route("/tutorials/<int:video_id>/pdf")
@login_required
def tutorial_pdf(video_id):
    ensure_training_playlist_schema()
    video = TrainingVideo.query.get_or_404(video_id)
    if not video.pdf_filename:
        abort(404)

    folder = Path(app.config["TRAINING_UPLOAD_FOLDER"])
    pdf_path = folder / video.pdf_filename
    if not pdf_path.exists():
        abort(404)

    download_name = video.pdf_original_name or pdf_path.name
    return send_from_directory(
        directory=str(folder),
        path=video.pdf_filename,
        as_attachment=True,
        download_name=download_name,
    )


# ============================================================
# Routen: Neue Orders + Datei-Upload
# ============================================================

@app.route("/orders/new", methods=["GET", "POST"])
@login_required
def new_order():
    """
    Formular zum Anlegen eines neuen Auftrags.
    Optional: direkter Upload einer 3D-Datei (STL/3MF) beim Erstellen.
    """
    # Stammdaten laden (f├╝r GET und POST)
    ensure_order_project_columns()
    ensure_order_estimation_columns()
    ensure_order_archive_columns()
    ensure_order_category_schema()
    ensure_order_area_schema()

    cost_centers = CostCenter.query.filter_by(is_active=True).order_by(CostCenter.name.asc()).all()
    order_categories = OrderCategory.query.filter_by(active=True).order_by(OrderCategory.name.asc()).all()
    order_areas = OrderArea.query.order_by(OrderArea.name.asc()).all()
    trans = inject_globals().get("t")
    status_context = get_status_context(trans)

    if request.method == "POST":
        form_token = (request.form.get("form_token") or "").strip()
        expected_token = session.pop("new_order_form_token", None)
        if not form_token or not expected_token or form_token != expected_token:
            app.logger.warning(
                "[new_order] Duplicate or invalid form submission ignored for user=%s",
                current_user.email,
            )
            write_audit_log(
                app,
                "order_create_duplicate_ignored",
                user=current_user,
                level="warning",
                details={"title": request.form.get("title", "").strip()},
            )
            flash(trans("flash_duplicate_submission_ignored"), "warning")
            return redirect(url_for("dashboard"))

        title = request.form.get("title", "").strip()
        description = request.form.get("description", "").strip()

        # --- Status-Handling ---
        if current_user.role == "admin":
            # Admin darf initialen Status w├ñhlen
            status = "new"
        else:
            # Normale Nutzer starten immer mit "new"
            status = "new"
        # ------------------------

        # Kostenstelle / Druckerprofil / Filament (optional)
        cost_center_id = request.form.get("cost_center_id") or None
        category_id = request.form.get("category_id") or None
        area_id = request.form.get("area_id") or None
        selected_category = None
        selected_area = None
        if category_id:
            try:
                selected_category_id = int(category_id)
            except ValueError:
                selected_category_id = None
            if selected_category_id:
                selected_category = OrderCategory.query.filter_by(
                    id=selected_category_id,
                    active=True,
                ).first()
        if selected_category is None:
            selected_category = OrderCategory.query.filter_by(key="3d_print", active=True).first()

        if area_id:
            try:
                selected_area_id = int(area_id)
            except ValueError:
                selected_area_id = None
            if selected_area_id:
                selected_area = OrderArea.query.filter_by(id=selected_area_id).first()

        # ├ûffentlichkeits-Felder
        def _default_public_flag(field_name: str) -> bool:
            val = request.form.get(field_name)
            if val is None:
                return True
            return bool(val)

        public_allow_poster = _default_public_flag("public_allow_poster")
        public_allow_web = _default_public_flag("public_allow_web")
        public_allow_social = _default_public_flag("public_allow_social")
        public_display_name = request.form.get("public_display_name", "").strip() or None

        summary_short = request.form.get("summary_short", "").strip() or None
        summary_long = request.form.get("summary_long", "").strip() or None
        project_group = request.form.get("project_group", "").strip() or None
        project_purpose = request.form.get("project_purpose", "").strip() or None
        project_use_case = request.form.get("project_use_case", "").strip() or None
        learning_points = request.form.get("learning_points", "").strip() or None
        background_info = request.form.get("background_info", "").strip() or None
        project_url = request.form.get("project_url", "").strip() or None
        tags_value = request.form.get("tags", "").strip() or None
        language = request.form.get("language", "").strip().lower() or "en"
        if language not in SUPPORTED_LANGS:
            language = "en"

        if not title:
            form_token = secrets.token_urlsafe(24)
            session["new_order_form_token"] = form_token
            flash(trans("flash_title_required"), "danger")
            return render_template(
                "orders_new.html",
                form_token=form_token,
                cost_centers=cost_centers,
                order_categories=order_categories,
                order_areas=order_areas,
            )

        if selected_area is None:
            form_token = secrets.token_urlsafe(24)
            session["new_order_form_token"] = form_token
            flash(trans("flash_order_area_required"), "danger")
            return render_template(
                "orders_new.html",
                form_token=form_token,
                cost_centers=cost_centers,
                order_categories=order_categories,
                order_areas=order_areas,
            )

        order = Order(
            id=reserve_next_order_id(),
            title=title,
            description=description or None,
            status=status,
            category_id=selected_category.id if selected_category else None,
            area_id=selected_area.id if selected_area else None,
            user_id=current_user.id,
            public_allow_poster=public_allow_poster,
            public_allow_web=public_allow_web,
            public_allow_social=public_allow_social,
            public_display_name=public_display_name,
            summary_short=summary_short,
            summary_long=summary_long,
            project_group=project_group,
            project_purpose=project_purpose,
            project_use_case=project_use_case,
            learning_points=learning_points,
            background_info=background_info,
            project_url=project_url,
        )

        def _select_id(model, raw_id):
            if not raw_id:
                return None
            try:
                raw_int = int(raw_id)
            except ValueError:
                return None
            entry = model.query.get(raw_int)
            return entry.id if entry else None

        # Nur sinnvolle IDs setzen
        if cost_center_id:
            try:
                selected_cost_center_id = int(cost_center_id)
            except ValueError:
                selected_cost_center_id = None
            if selected_cost_center_id:
                selected_cost_center = CostCenter.query.filter_by(
                    id=selected_cost_center_id,
                    is_active=True,
                ).first()
                if selected_cost_center:
                    order.cost_center_id = selected_cost_center.id

        db.session.add(order)
        db.session.commit()
        write_audit_log(
            app,
            "order_created",
            user=current_user,
            details={
                "order_id": order.id,
                "title": order.title,
                "status": order.status,
                "category_id": order.category_id,
                "area_id": order.area_id,
                "cost_center_id": order.cost_center_id,
            },
        )

        # Tags speichern
        if tags_value:
            db.session.add(OrderTag(order_id=order.id, tags=tags_value))
            db.session.commit()

        # === Datei-Upload (optional) =======================================
        file = request.files.get("model_file")
        if file and file.filename:
            original_name = file.filename
            safe_name = secure_filename(original_name)

            # Dateityp/Endung bestimmen (ohne Punkt)
            _, ext = os.path.splitext(safe_name)
            ext = ext.lower().lstrip(".")  # "stl" oder "3mf"

            allowed_ext = {"stl", "3mf"}
            if ext not in allowed_ext:
                flash(trans("flash_invalid_file"), "warning")
            else:
                # OrderFile-Eintrag mit Platzhalter speichern
                order_file = OrderFile(
                    order_id=order.id,
                    original_name=original_name,
                    stored_name="",
                    file_type=ext,
                    material_id=_select_id(Material, request.form.get("file_material_id")),
                    color_id=_select_id(Color, request.form.get("file_color_id")),
                )
                db.session.add(order_file)
                db.session.flush()  # gibt uns eine ID, ohne zu committen

                # Eindeutigen Dateinamen bauen: <id>_<safe_name>
                stored_name = f"{order_file.id}_{safe_name}"

                # Unterordner pro Order
                order_folder = Path(app.config["UPLOAD_FOLDER"]) / f"order_{order.id}"
                order_folder.mkdir(parents=True, exist_ok=True)

                full_path = order_folder / stored_name
                file.save(str(full_path))

                # Metadaten aktualisieren
                order_file.stored_name = stored_name
                try:
                    order_file.filesize = full_path.stat().st_size
                except OSError:
                    order_file.filesize = None

                order_file.uploaded_at = datetime.utcnow()
                update_order_file_preview(order_file, full_path)

                db.session.commit()
                write_audit_log(
                    app,
                    "file_uploaded",
                    user=current_user,
                    details={
                        "order_id": order.id,
                        "file_kind": "model",
                        "file_id": order_file.id,
                        "original_name": order_file.original_name,
                        "stored_name": order_file.stored_name,
                        "file_type": order_file.file_type,
                        "filesize": order_file.filesize,
                        "material_id": order_file.material_id,
                        "color_id": order_file.color_id,
                    },
                )

                app.logger.debug(
                    f"[new_order] Uploaded file for order {order.id}: "
                    f"OrderFile.id={order_file.id}, stored_name={stored_name!r}"
                )
        # ===================================================================

        app.logger.debug(
            f"[new_order] Created order id={order.id}, title={order.title!r}, "
            f"status={order.status!r}, user={current_user.email}"
        )

        send_admin_order_notification(app, order, status_context["order_status_labels"])
        flash(trans("flash_order_created"), "success")
        return redirect(url_for("dashboard"))

    # GET
    form_token = secrets.token_urlsafe(24)
    session["new_order_form_token"] = form_token
    return render_template(
        "orders_new.html",
        form_token=form_token,
        cost_centers=cost_centers,
        order_categories=order_categories,
        order_areas=order_areas,
    )


# ============================================================
# Routen: Order-Details (inkl. Chat & Dateien)
# ============================================================

@app.route("/orders/<int:order_id>", methods=["GET", "POST"])
@login_required
def order_detail(order_id):
    """
    Detailansicht eines Auftrags:
    - Stammdaten bearbeiten
    - Status ├ñndern (nur Admin)
    - Nachrichten schreiben
    - Dateien hochladen / l├Âschen
    """
    order = Order.query.get_or_404(order_id)

    # Access control: normale User sehen nur eigene Auftr├ñge
    if not can_view_order(order, current_user):
        abort(403)

    visible_tabs = get_visible_order_tabs(order, current_user)
    valid_tabs = set(visible_tabs)
    active_tab = request.args.get("tab", "general")
    if active_tab not in valid_tabs:
        active_tab = "general"

    def order_detail_redirect(tab="general"):
        if tab in valid_tabs and tab != "general":
            return redirect(url_for("order_detail", order_id=order.id, tab=tab))
        return redirect(url_for("order_detail", order_id=order.id))

    if request.method == "POST":
        app.logger.debug(f"[order_detail] POST data for order {order.id}: {dict(request.form)}")
        trans = inject_globals().get("t")

        action = request.form.get("action")

        # --- 1) Auftragsdaten aktualisieren --------------------------------
        if action == "update_order":
            title = request.form.get("title", "").strip()
            description = request.form.get("description", "").strip()
            area_id_raw = request.form.get("area_id", "").strip()
            status = request.form.get("status", order.status)
            previous_status = order.status

            public_allow_poster = bool(request.form.get("public_allow_poster"))
            public_allow_web = bool(request.form.get("public_allow_web"))
            public_allow_social = bool(request.form.get("public_allow_social"))
            public_display_name = request.form.get("public_display_name", "").strip() or None

            summary_short = request.form.get("summary_short", "").strip() or None
            summary_long = request.form.get("summary_long", "").strip() or None
            project_group = request.form.get("project_group", "").strip() or None
            project_purpose = request.form.get("project_purpose", "").strip() or None
            project_use_case = request.form.get("project_use_case", "").strip() or None
            learning_points = request.form.get("learning_points", "").strip() or None
            background_info = request.form.get("background_info", "").strip() or None
            project_url = request.form.get("project_url", "").strip() or None
            tags_value = request.form.get("tags", "").strip() or None

            app.logger.debug(
                f"[order_detail] UPDATE_ORDER before: id={order.id}, "
                f"title={order.title!r}, status={order.status!r}"
            )
            app.logger.debug(f"[order_detail] Form status value: {status!r}")

            if not title:
                flash(trans("flash_title_required"), "danger")
            else:
                try:
                    selected_area_id = int(area_id_raw)
                except (TypeError, ValueError):
                    selected_area_id = None
                selected_area = OrderArea.query.filter_by(id=selected_area_id).first() if selected_area_id else None

                if selected_area is None:
                    flash(trans("flash_order_area_required"), "danger")
                    return redirect(url_for("order_detail", order_id=order.id, tab="general"))

                order.title = title
                order.description = description or None
                order.area_id = selected_area.id

                # Kostenstelle aktualisieren (f├╝r alle Rollen erlaubt)
                cost_center_id = request.form.get("cost_center_id") or None
                current_printer_profile_id = order.printer_profile_id
                current_filament_material_id = order.filament_material_id

                if cost_center_id:
                    try:
                        selected_cost_center_id = int(cost_center_id)
                    except ValueError:
                        selected_cost_center_id = None
                    selected_cost_center = (
                        CostCenter.query
                        .filter_by(id=selected_cost_center_id, is_active=True)
                        .first()
                        if selected_cost_center_id
                        else None
                    )
                    order.cost_center_id = selected_cost_center.id if selected_cost_center else None
                else:
                    order.cost_center_id = None

                def _select_profile_id(model, raw_id, current_id):
                    if raw_id in (None, "", "null"):
                        return None
                    try:
                        raw_int = int(raw_id)
                    except ValueError:
                        return current_id
                    entry = model.query.filter_by(id=raw_int).first()
                    if not entry:
                        return current_id
                    if not entry.active and raw_int != current_id:
                        return current_id
                    return entry.id

                if "printer_profile_id" in request.form:
                    printer_profile_id = request.form.get("printer_profile_id") or None
                    order.printer_profile_id = _select_profile_id(
                        PrinterProfile,
                        printer_profile_id,
                        current_printer_profile_id,
                    )
                if "filament_material_id" in request.form:
                    filament_material_id = request.form.get("filament_material_id") or None
                    order.filament_material_id = _select_profile_id(
                        FilamentMaterial,
                        filament_material_id,
                        current_filament_material_id,
                    )

                # ├ûffentlichkeits-Felder ├╝bernehmen
                order.public_allow_poster = public_allow_poster
                order.public_allow_web = public_allow_web
                order.public_allow_social = public_allow_social
                order.public_display_name = public_display_name
                order.summary_short = summary_short
                order.summary_long = summary_long
                order.project_group = project_group
                order.project_purpose = project_purpose
                order.project_use_case = project_use_case
                order.learning_points = learning_points
                order.background_info = background_info
                order.project_url = project_url

                # Tags upsert
                if tags_value:
                    if order.tags_entry:
                        order.tags_entry.tags = tags_value
                    else:
                        order.tags_entry = OrderTag(tags=tags_value)
                else:
                    if order.tags_entry:
                        db.session.delete(order.tags_entry)
                        order.tags_entry = None

                # Statuswechsel nur f├╝r Admin
                if current_user.role == "admin":
                    valid_status_values = ORDER_STATUS_VALUES
                    app.logger.debug(f"[order_detail] Valid status values: {valid_status_values}")
                    if status in valid_status_values:
                        order.status = status
                        app.logger.debug(f"[order_detail] Status changed to: {order.status!r}")
                    else:
                        app.logger.debug("[order_detail] Ignored invalid status from form.")

                db.session.commit()
                app.logger.debug(
                    f"[order_detail] UPDATE_ORDER after commit: id={order.id}, "
                    f"title={order.title!r}, status={order.status!r}"
                )

                if previous_status != order.status:
                    status_labels = get_status_context(trans).get("order_status_labels", {})
                    _send_relevant_order_status_email(app, order, previous_status, status_labels)
                flash(trans("flash_order_updated"), "success")
                return redirect(url_for("order_detail", order_id=order.id))

        # --- 2) Neue Nachricht hinzuf├╝gen ----------------------------------
        elif action == "add_message":
            content = request.form.get("content", "").strip()
            app.logger.debug(f"[order_detail] ADD_MESSAGE for order {order.id}: {content!r}")

            if not content:
                flash(trans("flash_enter_message"), "danger")
            else:
                msg = OrderMessage(
                    order_id=order.id,
                    user_id=current_user.id,
                    content=content,
                )
                db.session.add(msg)
                db.session.commit()
                app.logger.debug(f"[order_detail] Message {msg.id} added to order {order.id}")
                flash(trans("flash_message_added"), "success")
                return redirect(url_for("order_detail", order_id=order.id))

        # --- 3) Auftrag stornieren -----------------------------------------
        elif action == "cancel_order":
            app.logger.debug(
                f"[order_detail] CANCEL_ORDER requested by user={current_user.email}, "
                f"order_id={order.id}, current_status={order.status!r}"
            )
            previous_status = order.status
            # User darf nur eigene Auftr├ñge stornieren, Admin alle
            if current_user.role == "admin" or order.user_id == current_user.id:
                if order.status not in ("completed", "cancelled"):
                    order.status = "cancelled"
                    db.session.commit()
                    app.logger.debug(
                        f"[order_detail] Order {order.id} cancelled. New status={order.status!r}"
                    )
                    status_labels = get_status_context(trans).get("order_status_labels", {})
                    send_order_status_change_notification(
                        app,
                        order,
                        previous_status,
                        order.status,
                        status_labels,
                    )
                    flash(trans("flash_order_cancelled"), "info")
                else:
                    app.logger.debug(
                        f"[order_detail] Order {order.id} cannot be cancelled (status={order.status!r})"
                    )
                    flash(trans("flash_order_cannot_cancel"), "warning")
            else:
                app.logger.debug(
                    f"[order_detail] CANCEL_ORDER forbidden for user={current_user.email}, "
                    f"order_id={order.id}"
                )

            return redirect(url_for("order_detail", order_id=order.id))

        # --- 4) Zus├ñtzliche Datei hochladen --------------------------------
        elif action == "upload_file":
            file = request.files.get("model_file")
            file_note = request.form.get("file_note", "").strip() or None
            file_material_id = request.form.get("file_material_id") or None
            file_color_id = request.form.get("file_color_id") or None
            file_quantity_raw = request.form.get("file_quantity", "").strip()
            try:
                file_quantity = max(1, int(file_quantity_raw or "1"))
            except ValueError:
                file_quantity = 1

            if not file or not file.filename:
                flash(trans("flash_select_file"), "warning")
                return order_detail_redirect("files")

            original_name = file.filename
            safe_name = secure_filename(original_name)

            _, ext = os.path.splitext(safe_name)
            ext = ext.lower().lstrip(".")  # "stl" oder "3mf"

            allowed_ext = {"stl", "3mf"}
            if ext not in allowed_ext:
                flash(trans("flash_invalid_file"), "warning")
                return order_detail_redirect("files")

            # OrderFile-Eintrag mit Platzhalter
            order_file = OrderFile(
                order_id=order.id,
                original_name=original_name,
                stored_name="",
                file_type=ext,
                note=file_note,
                quantity=file_quantity,
            )
            if file_material_id:
                try:
                    material_id_int = int(file_material_id)
                    if Material.query.get(material_id_int):
                        order_file.material_id = material_id_int
                except ValueError:
                    pass
            if file_color_id:
                try:
                    color_id_int = int(file_color_id)
                    if Color.query.get(color_id_int):
                        order_file.color_id = color_id_int
                except ValueError:
                    pass
            db.session.add(order_file)
            db.session.flush()  # gibt eine ID ohne Commit

            # eindeutiger Dateiname
            stored_name = f"{order_file.id}_{safe_name}"

            order_folder = Path(app.config["UPLOAD_FOLDER"]) / f"order_{order.id}"
            order_folder.mkdir(parents=True, exist_ok=True)

            full_path = order_folder / stored_name
            file.save(str(full_path))

            try:
                order_file.filesize = full_path.stat().st_size
            except OSError:
                order_file.filesize = None

            order_file.stored_name = stored_name
            order_file.uploaded_at = datetime.utcnow()
            update_order_file_preview(order_file, full_path)

            db.session.commit()
            write_audit_log(
                app,
                "file_uploaded",
                user=current_user,
                details={
                    "order_id": order.id,
                    "file_kind": "model",
                    "file_id": order_file.id,
                    "original_name": order_file.original_name,
                    "stored_name": order_file.stored_name,
                    "file_type": order_file.file_type,
                    "filesize": order_file.filesize,
                    "quantity": order_file.quantity,
                    "material_id": order_file.material_id,
                    "color_id": order_file.color_id,
                },
            )

            app.logger.debug(
                f"[order_detail] Uploaded extra file for order {order.id}: "
                f"OrderFile.id={order_file.id}, stored_name={stored_name!r}"
            )

            flash(trans("flash_file_uploaded"), "success")
            return order_detail_redirect("files")

        # --- 4b) Datei bearbeiten (Notiz + Anzahl) ----------------------------
        elif action == "update_file":
            try:
                file_id = int(request.form.get("file_id", "0"))
            except ValueError:
                file_id = 0

            if not file_id:
                flash(trans("flash_invalid_file_id"), "danger")
                return redirect(url_for("order_detail", order_id=order.id))

            order_file = OrderFile.query.filter_by(
                id=file_id,
                order_id=order.id,
            ).first()

            if not order_file:
                flash(trans("flash_file_not_found"), "warning")
                return redirect(url_for("order_detail", order_id=order.id))

            file_note_raw = request.form.get("file_note", "").strip()
            file_note = file_note_raw[:255] if file_note_raw else None
            file_material_id = request.form.get("file_material_id") or None
            file_color_id = request.form.get("file_color_id") or None
            file_quantity_raw = request.form.get("file_quantity", "").strip()
            try:
                file_quantity = max(1, int(file_quantity_raw or "1"))
            except ValueError:
                file_quantity = 1

            order_file.note = file_note
            order_file.quantity = file_quantity
            order_file.material_id = None
            if file_material_id:
                try:
                    material_id_int = int(file_material_id)
                    if Material.query.get(material_id_int):
                        order_file.material_id = material_id_int
                except ValueError:
                    pass
            order_file.color_id = None
            if file_color_id:
                try:
                    color_id_int = int(file_color_id)
                    if Color.query.get(color_id_int):
                        order_file.color_id = color_id_int
                except ValueError:
                    pass
            db.session.commit()

            flash(trans("flash_file_updated"), "success")
            return order_detail_redirect("files")

        # --- 5) Projektbild hochladen --------------------------------------
        elif action == "upload_image":
            file = request.files.get("image_file")
            image_note = (request.form.get("image_note") or "").strip()
            if image_note:
                image_note = image_note[:255]
            if not file or not file.filename:
                flash(trans("flash_select_image"), "warning")
                return order_detail_redirect("files")

            original_name = file.filename
            safe_name = secure_filename(original_name)

            _, ext = os.path.splitext(safe_name)
            ext = ext.lower().lstrip(".")

            allowed_ext = {"png", "jpg", "jpeg", "gif", "webp"}
            if ext not in allowed_ext:
                flash(trans("flash_invalid_image"), "warning")
                return order_detail_redirect("files")

            image_entry = OrderImage(
                order_id=order.id,
                original_name=original_name,
                stored_name="",
                note=image_note or None,
            )
            db.session.add(image_entry)
            db.session.flush()

            stored_name = f"{image_entry.id}_{safe_name}"

            image_folder = Path(app.config["IMAGE_UPLOAD_FOLDER"]) / f"order_{order.id}"
            image_folder.mkdir(parents=True, exist_ok=True)

            full_path = image_folder / stored_name
            file.save(str(full_path))

            thumb_folder = image_folder / "thumbnails"
            thumb_path = thumb_folder / stored_name
            save_image_thumbnail(full_path, thumb_path)

            try:
                image_entry.filesize = full_path.stat().st_size
            except OSError:
                image_entry.filesize = None

            image_entry.stored_name = stored_name
            image_entry.uploaded_at = datetime.utcnow()

            db.session.commit()
            write_audit_log(
                app,
                "file_uploaded",
                user=current_user,
                details={
                    "order_id": order.id,
                    "file_kind": "image",
                    "file_id": image_entry.id,
                    "original_name": image_entry.original_name,
                    "stored_name": image_entry.stored_name,
                    "filesize": image_entry.filesize,
                },
            )

            flash(trans("flash_image_uploaded"), "success")
            return order_detail_redirect("files")

        # --- 5b) Projektbild bearbeiten (Notiz) ------------------------------
        elif action == "update_image":
            try:
                image_id = int(request.form.get("image_id", "0"))
            except ValueError:
                image_id = 0

            if not image_id:
                flash(trans("flash_invalid_image_id"), "danger")
                return redirect(url_for("order_detail", order_id=order.id))

            image_entry = OrderImage.query.filter_by(
                id=image_id,
                order_id=order.id,
            ).first()

            if not image_entry:
                flash(trans("flash_image_not_found"), "warning")
                return redirect(url_for("order_detail", order_id=order.id))

            image_note_raw = (request.form.get("image_note") or "").strip()
            image_entry.note = image_note_raw[:255] if image_note_raw else None
            db.session.commit()

            flash(trans("flash_image_updated"), "success")
            return redirect(url_for("order_detail", order_id=order.id))

        # --- 5c) Projektvideo hochladen -------------------------------------
        elif action == "upload_video":
            file = request.files.get("video_file")
            video_note = (request.form.get("video_note") or "").strip()
            if video_note:
                video_note = video_note[:255]
            if not file or not file.filename:
                flash(trans("flash_select_video"), "warning")
                return order_detail_redirect("files")

            original_name = file.filename
            safe_name = secure_filename(original_name)
            _, ext = os.path.splitext(safe_name)
            ext = ext.lower().lstrip(".")

            allowed_ext = {"mp4", "webm", "ogv", "ogg", "mov"}
            if ext not in allowed_ext:
                flash(trans("flash_invalid_video"), "warning")
                return order_detail_redirect("files")

            video_entry = OrderVideo(
                order_id=order.id,
                original_name=original_name,
                stored_name="",
                file_type=ext,
                note=video_note or None,
            )
            db.session.add(video_entry)
            db.session.flush()

            stored_name = f"{video_entry.id}_{safe_name}"
            video_folder = Path(app.config["VIDEO_UPLOAD_FOLDER"]) / f"order_{order.id}"
            video_folder.mkdir(parents=True, exist_ok=True)
            full_path = video_folder / stored_name
            file.save(str(full_path))

            try:
                video_entry.filesize = full_path.stat().st_size
            except OSError:
                video_entry.filesize = None

            if video_entry.filesize and video_entry.filesize > MAX_UPLOAD_SIZE_MB * 1024 * 1024:
                try:
                    full_path.unlink()
                except OSError:
                    app.logger.warning("[order_detail] Could not remove oversized video: %s", full_path)
                db.session.rollback()
                flash(trans("flash_upload_too_large"), "danger")
                return order_detail_redirect("files")

            video_entry.stored_name = stored_name
            video_entry.uploaded_at = datetime.utcnow()
            db.session.commit()
            write_audit_log(
                app,
                "file_uploaded",
                user=current_user,
                details={
                    "order_id": order.id,
                    "file_kind": "video",
                    "file_id": video_entry.id,
                    "original_name": video_entry.original_name,
                    "stored_name": video_entry.stored_name,
                    "file_type": video_entry.file_type,
                    "filesize": video_entry.filesize,
                },
            )

            flash(trans("flash_video_uploaded"), "success")
            return order_detail_redirect("files")

        # --- 5d) Projektvideo bearbeiten ------------------------------------
        elif action == "update_video":
            try:
                video_id = int(request.form.get("video_id", "0"))
            except ValueError:
                video_id = 0

            video_entry = OrderVideo.query.filter_by(
                id=video_id,
                order_id=order.id,
            ).first()
            if not video_entry:
                flash(trans("flash_video_not_found"), "warning")
                return order_detail_redirect("files")

            video_note = (request.form.get("video_note") or "").strip()
            video_entry.note = video_note[:255] if video_note else None
            db.session.commit()

            flash(trans("flash_video_updated"), "success")
            return order_detail_redirect("files")

        # --- 5c) Plakatdatei hochladen (nur Plotter-Auftraege) -------------
        elif action == "upload_poster_file":
            if not is_plotter_order(order):
                abort(403)

            file = request.files.get("poster_file")
            note = (request.form.get("poster_note") or "").strip()
            if note:
                note = note[:255]
            quantity_raw = (request.form.get("poster_quantity") or "").strip()
            due_date_raw = (request.form.get("poster_due_date") or "").strip()

            try:
                quantity = max(1, int(quantity_raw or "1"))
            except ValueError:
                quantity = 1

            due_date = None
            if due_date_raw:
                try:
                    due_date = datetime.strptime(due_date_raw, "%Y-%m-%d").date()
                except ValueError:
                    flash(trans("flash_poster_invalid_due_date"), "danger")
                    return order_detail_redirect("posters")

            if not file or not file.filename:
                flash(trans("flash_poster_select_file"), "warning")
                return order_detail_redirect("posters")

            original_name = file.filename
            safe_name = secure_filename(original_name)
            _, ext = os.path.splitext(safe_name)
            ext = ext.lower().lstrip(".")
            allowed_ext = {"jpg", "jpeg", "png", "pdf"}
            if ext not in allowed_ext:
                flash(trans("flash_poster_invalid_file"), "warning")
                return order_detail_redirect("posters")

            poster_file = OrderPosterFile(
                order_id=order.id,
                original_name=original_name,
                stored_name="",
                file_type=ext,
                note=note or None,
                status="open",
                quantity=quantity,
                due_date=due_date,
            )
            db.session.add(poster_file)
            db.session.flush()

            stored_name = f"{poster_file.id}_{safe_name}"
            order_folder = Path(app.config["POSTER_UPLOAD_FOLDER"]) / f"order_{order.id}"
            order_folder.mkdir(parents=True, exist_ok=True)
            full_path = order_folder / stored_name
            file.save(str(full_path))

            poster_file.stored_name = stored_name
            try:
                poster_file.filesize = full_path.stat().st_size
            except OSError:
                poster_file.filesize = None
            thumb_name = f"{poster_file.id}_{Path(safe_name).stem}.png"
            thumb_path = order_folder / "thumbnails" / thumb_name
            if save_poster_thumbnail(full_path, thumb_path, ext):
                poster_file.thumb_path = thumb_name
            poster_file.uploaded_at = datetime.utcnow()

            previous_status = order.status
            sync_plotter_order_status_from_posters(order)

            db.session.commit()
            _send_relevant_order_status_email(app, order, previous_status, get_status_context(trans).get("order_status_labels", {}))
            write_audit_log(
                app,
                "file_uploaded",
                user=current_user,
                details={
                    "order_id": order.id,
                    "file_kind": "poster",
                    "file_id": poster_file.id,
                    "original_name": poster_file.original_name,
                    "stored_name": poster_file.stored_name,
                    "file_type": poster_file.file_type,
                    "filesize": poster_file.filesize,
                    "quantity": poster_file.quantity,
                    "due_date": poster_file.due_date.isoformat() if poster_file.due_date else None,
                },
            )
            flash(trans("flash_poster_uploaded"), "success")
            return order_detail_redirect("posters")

        elif action == "update_poster_file":
            if not is_plotter_order(order):
                abort(403)

            try:
                poster_id = int(request.form.get("poster_id", "0"))
            except ValueError:
                poster_id = 0

            if not poster_id:
                flash(trans("flash_poster_invalid_id"), "danger")
                return order_detail_redirect("posters")

            poster_file = OrderPosterFile.query.filter_by(
                id=poster_id,
                order_id=order.id,
            ).first()
            if not poster_file:
                flash(trans("flash_poster_not_found"), "warning")
                return order_detail_redirect("posters")

            note = (request.form.get("poster_note") or "").strip()
            quantity_raw = (request.form.get("poster_quantity") or "").strip()
            due_date_raw = (request.form.get("poster_due_date") or "").strip()

            try:
                quantity = max(1, int(quantity_raw or "1"))
            except ValueError:
                quantity = 1

            due_date = None
            if due_date_raw:
                try:
                    due_date = datetime.strptime(due_date_raw, "%Y-%m-%d").date()
                except ValueError:
                    flash(trans("flash_poster_invalid_due_date"), "danger")
                    return order_detail_redirect("posters")

            poster_file.note = note[:255] if note else None
            poster_file.quantity = quantity
            poster_file.due_date = due_date
            previous_status = order.status
            sync_plotter_order_status_from_posters(order)
            db.session.commit()

            _send_relevant_order_status_email(app, order, previous_status, get_status_context(trans).get("order_status_labels", {}))

            flash(trans("flash_poster_updated"), "success")
            return order_detail_redirect("posters")

        elif action == "mark_poster_printed":
            if not is_plotter_order(order):
                abort(403)
            if current_user.role not in {"admin", "worker"}:
                abort(403)

            try:
                poster_id = int(request.form.get("poster_id", "0"))
            except ValueError:
                poster_id = 0

            if not poster_id:
                flash(trans("flash_poster_invalid_id"), "danger")
                return order_detail_redirect("posters")

            poster_file = OrderPosterFile.query.filter_by(
                id=poster_id,
                order_id=order.id,
            ).first()
            if not poster_file:
                flash(trans("flash_poster_not_found"), "warning")
                return order_detail_redirect("posters")

            was_marked = poster_file.status == "printed"
            if not was_marked:
                poster_file.status = "printed"
            previous_status = order.status
            sync_plotter_order_status_from_posters(order)
            db.session.commit()
            if not was_marked:
                flash(trans("flash_poster_marked_printed"), "success")
                send_poster_printed_notification(app, order, poster_file)
            else:
                flash(trans("flash_poster_already_printed"), "info")

            _send_relevant_order_status_email(app, order, previous_status, get_status_context(trans).get("order_status_labels", {}))

            return order_detail_redirect("posters")

        elif action == "delete_poster_file":
            if not is_plotter_order(order):
                abort(403)

            try:
                poster_id = int(request.form.get("poster_id", "0"))
            except ValueError:
                poster_id = 0

            if not poster_id:
                flash(trans("flash_poster_invalid_id"), "danger")
                return order_detail_redirect("posters")

            poster_file = OrderPosterFile.query.filter_by(
                id=poster_id,
                order_id=order.id,
            ).first()
            if not poster_file:
                flash(trans("flash_poster_not_found"), "warning")
                return order_detail_redirect("posters")

            if current_user.role == "user" and (poster_file.status or "open") == "printed":
                flash(trans("flash_poster_delete_printed_forbidden"), "warning")
                return order_detail_redirect("posters")

            order_folder = Path(app.config["POSTER_UPLOAD_FOLDER"]) / f"order_{order.id}"
            full_path = order_folder / poster_file.stored_name
            if full_path.exists():
                try:
                    full_path.unlink()
                except OSError:
                    app.logger.warning("Could not delete poster file on disk: %s", full_path)

            if poster_file.thumb_path:
                thumb_path = order_folder / "thumbnails" / poster_file.thumb_path
                if thumb_path.exists():
                    try:
                        thumb_path.unlink()
                    except OSError:
                        app.logger.warning("Could not delete poster thumbnail on disk: %s", thumb_path)

            db.session.delete(poster_file)
            db.session.flush()
            sync_plotter_order_status_from_posters(order)
            db.session.commit()

            flash(trans("flash_poster_deleted"), "info")
            return order_detail_redirect("posters")

        elif action == "send_procurement_article_list":
            if not is_procurement_order(order):
                abort(403)

            recipient = (request.form.get("article_list_email_recipient") or "").strip()
            if not recipient:
                flash(trans("flash_procurement_article_list_email_recipient_required"), "warning")
                return order_detail_redirect("articles")

            ensure_procurement_article_position_numbers(order.id)
            db.session.commit()
            articles = _procurement_articles_for_order(order)
            position_count = len(articles)
            total_price = sum(
                (article.price_per_unit_incl_vat or 0.0) * (article.quantity or 1)
                for article in articles
            )
            if not articles:
                flash(trans("flash_procurement_article_list_email_no_articles"), "warning")
                return order_detail_redirect("articles")

            sent = send_procurement_article_list_email(
                app,
                order,
                recipient,
                articles,
                position_count,
                total_price,
            )
            if sent:
                save_user_email_favorites(current_user.id, recipient)
                db.session.commit()
                flash(trans("flash_procurement_article_list_email_sent"), "success")
            else:
                flash(trans("flash_procurement_article_list_email_failed"), "danger")
            return order_detail_redirect("articles")

        elif action == "create_procurement_article":
            if not is_procurement_order(order):
                abort(403)

            article_name = (request.form.get("article_name") or "").strip()
            article_description = (request.form.get("article_description") or "").strip() or None
            supplier = (request.form.get("article_supplier") or "").strip() or None
            article_url = (request.form.get("article_url") or "").strip() or None
            quantity_raw = (request.form.get("article_quantity") or "").strip()
            price_raw = (request.form.get("article_price_per_unit_incl_vat") or "").strip()
            note_file = request.files.get("article_note_file")

            if not article_name:
                flash(trans("flash_procurement_article_name_required"), "warning")
                return order_detail_redirect("articles")

            try:
                quantity = max(1, int(quantity_raw or "1"))
            except ValueError:
                quantity = 1

            price_per_unit_incl_vat = None
            if price_raw:
                normalized_price = price_raw.replace(",", ".")
                try:
                    price_per_unit_incl_vat = float(normalized_price)
                except ValueError:
                    flash(trans("flash_procurement_invalid_price"), "danger")
                    return order_detail_redirect("articles")

            note_file_original_name = None
            note_file_stored_name = None
            note_file_type = None
            note_file_size = None

            if note_file and note_file.filename:
                note_file_original_name = note_file.filename
                safe_note_name = secure_filename(note_file_original_name)
                _, ext = os.path.splitext(safe_note_name)
                note_file_type = ext.lower().lstrip(".")
                allowed_note_ext = {"txt", "pdf", "doc", "docx", "odt", "ods", "odp", "odg", "odf", "rtf"}
                if note_file_type not in allowed_note_ext:
                    flash(trans("flash_procurement_invalid_note_file"), "warning")
                    return order_detail_redirect("articles")

            ensure_procurement_article_position_numbers(order.id)
            next_position_number = (
                db.session.query(func.max(OrderProcurementArticle.position_number))
                .filter_by(order_id=order.id)
                .scalar()
                or 0
            ) + 1

            article = OrderProcurementArticle(
                order_id=order.id,
                article_name=article_name[:255],
                status="open",
                article_description=article_description,
                supplier=supplier[:255] if supplier else None,
                article_url=article_url[:1000] if article_url else None,
                position_number=next_position_number,
                quantity=quantity,
                price_per_unit_incl_vat=price_per_unit_incl_vat,
                note_file_original_name=note_file_original_name,
                note_file_stored_name="" if note_file_original_name else None,
                note_file_type=note_file_type,
            )
            db.session.add(article)
            db.session.flush()
            previous_status = order.status

            if note_file and note_file.filename:
                safe_note_name = secure_filename(note_file_original_name or "note")
                note_file_stored_name = f"{article.id}_{safe_note_name}"
                note_folder = Path(app.config["PROCUREMENT_NOTE_UPLOAD_FOLDER"]) / f"order_{order.id}"
                note_folder.mkdir(parents=True, exist_ok=True)
                note_full_path = note_folder / note_file_stored_name
                note_file.save(str(note_full_path))
                article.note_file_stored_name = note_file_stored_name
                try:
                    note_file_size = note_full_path.stat().st_size
                except OSError:
                    note_file_size = None
                article.note_file_size = note_file_size

            sync_procurement_order_status_from_articles(order)
            db.session.commit()
            _send_relevant_order_status_email(
                app,
                order,
                previous_status,
                get_status_context(trans).get("order_status_labels", {}),
            )
            flash(trans("flash_procurement_article_created"), "success")
            return order_detail_redirect("articles")

        elif action == "update_procurement_article":
            if not is_procurement_order(order):
                abort(403)

            try:
                article_id = int(request.form.get("article_id", "0"))
            except ValueError:
                article_id = 0

            if not article_id:
                flash(trans("flash_procurement_article_not_found"), "warning")
                return order_detail_redirect("articles")

            article = OrderProcurementArticle.query.filter_by(id=article_id, order_id=order.id).first()
            if not article:
                flash(trans("flash_procurement_article_not_found"), "warning")
                return order_detail_redirect("articles")

            article_name = (request.form.get("article_name") or "").strip()
            article_description = (request.form.get("article_description") or "").strip() or None
            supplier = (request.form.get("article_supplier") or "").strip() or None
            article_url = (request.form.get("article_url") or "").strip() or None
            quantity_raw = (request.form.get("article_quantity") or "").strip()
            price_raw = (request.form.get("article_price_per_unit_incl_vat") or "").strip()

            if not article_name:
                flash(trans("flash_procurement_article_name_required"), "warning")
                return order_detail_redirect("articles")

            try:
                quantity = max(1, int(quantity_raw or "1"))
            except ValueError:
                quantity = 1

            price_per_unit_incl_vat = None
            if price_raw:
                normalized_price = price_raw.replace(",", ".")
                try:
                    price_per_unit_incl_vat = float(normalized_price)
                except ValueError:
                    flash(trans("flash_procurement_invalid_price"), "danger")
                    return order_detail_redirect("articles")

            article.article_name = article_name[:255]
            article.article_description = article_description
            article.supplier = supplier[:255] if supplier else None
            article.article_url = article_url[:1000] if article_url else None
            article.quantity = quantity
            article.price_per_unit_incl_vat = price_per_unit_incl_vat
            previous_status = order.status
            sync_procurement_order_status_from_articles(order)
            db.session.commit()
            _send_relevant_order_status_email(
                app,
                order,
                previous_status,
                get_status_context(trans).get("order_status_labels", {}),
            )

            flash(trans("flash_procurement_article_updated"), "success")
            return order_detail_redirect("articles")

        elif action == "mark_procurement_article_ordered":
            if not is_procurement_order(order):
                abort(403)
            if current_user.role not in {"admin", "worker"}:
                abort(403)

            try:
                article_id = int(request.form.get("article_id", "0"))
            except ValueError:
                article_id = 0

            if not article_id:
                flash(trans("flash_procurement_article_not_found"), "warning")
                return order_detail_redirect("articles")

            article = OrderProcurementArticle.query.filter_by(id=article_id, order_id=order.id).first()
            if not article:
                flash(trans("flash_procurement_article_not_found"), "warning")
                return order_detail_redirect("articles")

            previous_status = order.status
            all_articles_ordered_before = _all_procurement_articles_ordered(order)
            was_ordered = (article.status or "open").strip().lower() == "ordered"
            if not was_ordered:
                article.status = "ordered"
            sync_procurement_order_status_from_articles(order)
            db.session.commit()
            all_articles_ordered_after = _all_procurement_articles_ordered(order)

            if not all_articles_ordered_before and all_articles_ordered_after:
                _send_procurement_all_ordered_status_email(
                    app,
                    order,
                    previous_status,
                    get_status_context(trans).get("order_status_labels", {}),
                )
            else:
                _send_relevant_order_status_email(
                    app,
                    order,
                    previous_status,
                    get_status_context(trans).get("order_status_labels", {}),
                )

            if not was_ordered:
                flash(trans("flash_procurement_article_marked_ordered"), "success")
            else:
                flash(trans("flash_procurement_article_already_ordered"), "info")
            return order_detail_redirect("articles")

        elif action == "mark_procurement_article_delivered":
            if not is_procurement_order(order):
                abort(403)
            if current_user.role not in {"admin", "worker"}:
                abort(403)

            try:
                article_id = int(request.form.get("article_id", "0"))
            except ValueError:
                article_id = 0

            if not article_id:
                flash(trans("flash_procurement_article_not_found"), "warning")
                return order_detail_redirect("articles")

            article = OrderProcurementArticle.query.filter_by(id=article_id, order_id=order.id).first()
            if not article:
                flash(trans("flash_procurement_article_not_found"), "warning")
                return order_detail_redirect("articles")

            previous_status = order.status
            all_articles_ordered_before = _all_procurement_articles_ordered(order)
            was_delivered = (article.status or "open").strip().lower() == "delivered"
            if not was_delivered:
                article.status = "delivered"
            sync_procurement_order_status_from_articles(order)
            db.session.commit()
            all_articles_ordered_after = _all_procurement_articles_ordered(order)

            if not all_articles_ordered_before and all_articles_ordered_after:
                _send_procurement_all_ordered_status_email(
                    app,
                    order,
                    previous_status,
                    get_status_context(trans).get("order_status_labels", {}),
                )
            else:
                _send_relevant_order_status_email(
                    app,
                    order,
                    previous_status,
                    get_status_context(trans).get("order_status_labels", {}),
                )

            if not was_delivered:
                flash(trans("flash_procurement_article_marked_delivered"), "success")
            else:
                flash(trans("flash_procurement_article_already_delivered"), "info")
            return order_detail_redirect("articles")

        elif action == "delete_procurement_article":
            if not is_procurement_order(order):
                abort(403)

            try:
                article_id = int(request.form.get("article_id", "0"))
            except ValueError:
                article_id = 0

            if not article_id:
                flash(trans("flash_procurement_article_not_found"), "warning")
                return order_detail_redirect("articles")

            article = OrderProcurementArticle.query.filter_by(id=article_id, order_id=order.id).first()
            if not article:
                flash(trans("flash_procurement_article_not_found"), "warning")
                return order_detail_redirect("articles")

            if article.note_file_stored_name:
                note_folder = Path(app.config["PROCUREMENT_NOTE_UPLOAD_FOLDER"]) / f"order_{order.id}"
                note_full_path = note_folder / article.note_file_stored_name
                if note_full_path.exists():
                    try:
                        note_full_path.unlink()
                    except OSError:
                        app.logger.warning("Could not delete procurement note file on disk: %s", note_full_path)

            db.session.delete(article)
            db.session.flush()
            previous_status = order.status
            sync_procurement_order_status_from_articles(order)
            db.session.commit()
            _send_relevant_order_status_email(
                app,
                order,
                previous_status,
                get_status_context(trans).get("order_status_labels", {}),
            )

            flash(trans("flash_procurement_article_deleted"), "info")
            return order_detail_redirect("articles")

        # --- 6) G-Code hochladen (Admin + Mitarbeiter) ---------------------
        elif action == "upload_print_job":
            if current_user.role not in {"admin", "worker"} or not is_3d_print_order(order):
                abort(403)

            file = request.files.get("gcode_file")
            note = (request.form.get("gcode_note") or "").strip()
            if note:
                note = note[:255]

            started_at_raw = (request.form.get("print_started_at") or "").strip()
            duration_raw = (request.form.get("print_duration_min") or "").strip()
            filament_m_raw = (request.form.get("print_filament_m") or "").strip()
            filament_g_raw = (request.form.get("print_filament_g") or "").strip()
            quantity_raw = (request.form.get("print_quantity") or "").strip()
            status_raw = (request.form.get("print_status") or "").strip() or "upload"

            if not file or not file.filename:
                flash(trans("flash_print_job_select_file"), "warning")
                return order_detail_redirect("print-jobs")

            original_name = file.filename
            safe_name = secure_filename(original_name)

            _, ext = os.path.splitext(safe_name)
            ext = ext.lower().lstrip(".")
            allowed_ext = {"gcode", "gco", "gc"}
            if ext not in allowed_ext:
                flash(trans("flash_print_job_invalid_file"), "warning")
                return order_detail_redirect("print-jobs")

            started_at = None
            if started_at_raw:
                try:
                    started_at = parse_app_datetime_input(started_at_raw, load_app_settings(app))
                except ValueError:
                    flash(trans("flash_print_job_invalid_start"), "danger")
                    return order_detail_redirect("print-jobs")

            duration_min = None
            if duration_raw:
                try:
                    duration_min = int(duration_raw)
                except ValueError:
                    flash(trans("flash_print_job_invalid_duration"), "danger")
                    return order_detail_redirect("print-jobs")
                if duration_min < 0:
                    flash(trans("flash_print_job_invalid_duration"), "danger")
                    return order_detail_redirect("print-jobs")

            filament_m = None
            if filament_m_raw:
                try:
                    filament_m = float(filament_m_raw)
                except ValueError:
                    flash(trans("flash_print_job_invalid_filament"), "danger")
                    return order_detail_redirect("print-jobs")
                if filament_m < 0:
                    flash(trans("flash_print_job_invalid_filament"), "danger")
                    return order_detail_redirect("print-jobs")

            filament_g = None
            if filament_g_raw:
                try:
                    filament_g = float(filament_g_raw)
                except ValueError:
                    flash(trans("flash_print_job_invalid_filament"), "danger")
                    return order_detail_redirect("print-jobs")
                if filament_g < 0:
                    flash(trans("flash_print_job_invalid_filament"), "danger")
                    return order_detail_redirect("print-jobs")

            try:
                quantity = max(1, int(quantity_raw or "1"))
            except ValueError:
                quantity = 1

            valid_statuses = set(PRINT_JOB_STATUS_VALUES)
            status = status_raw if status_raw in valid_statuses else "upload"
            if status == "started":
                started_at = current_print_start_time()

            printer_profile_id = request.form.get("printer_profile_id") or None
            filament_material_id = request.form.get("filament_material_id") or None

            def _select_profile_id(model, raw_id, current_id):
                if raw_id in (None, "", "null"):
                    return None
                try:
                    raw_int = int(raw_id)
                except ValueError:
                    return current_id
                entry = model.query.filter_by(id=raw_int).first()
                if not entry:
                    return current_id
                if not entry.active and raw_int != current_id:
                    return current_id
                return entry.id

            selected_printer_profile_id = _select_profile_id(
                PrinterProfile,
                printer_profile_id,
                None,
            )
            selected_filament_material_id = _select_profile_id(
                FilamentMaterial,
                filament_material_id,
                None,
            )

            job = OrderPrintJob(
                order_id=order.id,
                printer_profile_id=selected_printer_profile_id,
                filament_material_id=selected_filament_material_id,
                original_name=original_name,
                stored_name="",
                note=note or None,
                status=status,
                started_at=started_at,
                duration_min=duration_min,
                filament_m=filament_m,
                filament_g=filament_g,
                quantity=quantity,
            )
            db.session.add(job)
            db.session.flush()

            stored_name = f"{job.id}_{safe_name}"
            order_folder = Path(app.config["GCODE_UPLOAD_FOLDER"]) / f"order_{order.id}"
            order_folder.mkdir(parents=True, exist_ok=True)
            full_path = order_folder / stored_name
            file.save(str(full_path))

            job.stored_name = stored_name
            try:
                job.filesize = full_path.stat().st_size
            except OSError:
                job.filesize = None
            job.uploaded_at = datetime.utcnow()
            gcode_metadata = extract_gcode_metadata(full_path)
            if duration_min is None:
                job.duration_min = int(gcode_metadata["duration_min"]) if "duration_min" in gcode_metadata else None
            if filament_m is None:
                job.filament_m = round(float(gcode_metadata["filament_m"]), 2) if "filament_m" in gcode_metadata else None
            if filament_g is None:
                job.filament_g = round(float(gcode_metadata["filament_g"]), 2) if "filament_g" in gcode_metadata else None

            previous_status = order.status
            # Beim ersten Druckauftrag soll ein neuer Auftrag automatisch in Bearbeitung gehen.
            if order.status in ("new", "neu"):
                order.status = "in_progress"

            sync_3d_order_status_from_print_jobs(order)

            db.session.commit()
            _send_relevant_order_status_email(app, order, previous_status, get_status_context(trans).get("order_status_labels", {}))
            write_audit_log(
                app,
                "file_uploaded",
                user=current_user,
                details={
                    "order_id": order.id,
                    "file_kind": "print_job",
                    "file_id": job.id,
                    "original_name": job.original_name,
                    "stored_name": job.stored_name,
                    "status": job.status,
                    "filesize": job.filesize,
                    "gcode_metadata": gcode_metadata,
                },
            )
            flash(trans("flash_print_job_uploaded"), "success")
            return order_detail_redirect("print-jobs")

        # --- 7) G-Code bearbeiten (Admin + Mitarbeiter) ---------------------
        elif action == "update_print_job":
            if current_user.role not in {"admin", "worker"} or not is_3d_print_order(order):
                abort(403)

            try:
                job_id = int(request.form.get("print_job_id", "0"))
            except ValueError:
                job_id = 0

            if not job_id:
                flash(trans("flash_print_job_invalid_id"), "danger")
                return redirect(url_for("order_detail", order_id=order.id))

            job = OrderPrintJob.query.filter_by(
                id=job_id,
                order_id=order.id,
            ).first()

            if not job:
                flash(trans("flash_print_job_not_found"), "warning")
                return redirect(url_for("order_detail", order_id=order.id))

            note = (request.form.get("edit_print_note") or "").strip()
            if note:
                note = note[:255]

            started_at_raw = (request.form.get("edit_print_started_at") or "").strip()
            duration_raw = (request.form.get("edit_print_duration_min") or "").strip()
            filament_m_raw = (request.form.get("edit_print_filament_m") or "").strip()
            filament_g_raw = (request.form.get("edit_print_filament_g") or "").strip()
            quantity_raw = (request.form.get("edit_print_quantity") or "").strip()
            status_raw = (request.form.get("edit_print_status") or "").strip()
            printer_profile_id = request.form.get("edit_printer_profile_id") or None
            filament_material_id = request.form.get("edit_filament_material_id") or None

            started_at = None
            if started_at_raw:
                try:
                    started_at = parse_app_datetime_input(started_at_raw, load_app_settings(app))
                except ValueError:
                    flash(trans("flash_print_job_invalid_start"), "danger")
                    return redirect(url_for("order_detail", order_id=order.id))

            duration_min = None
            if duration_raw:
                try:
                    duration_min = int(duration_raw)
                except ValueError:
                    flash(trans("flash_print_job_invalid_duration"), "danger")
                    return redirect(url_for("order_detail", order_id=order.id))
                if duration_min < 0:
                    flash(trans("flash_print_job_invalid_duration"), "danger")
                    return redirect(url_for("order_detail", order_id=order.id))

            filament_m = None
            if filament_m_raw:
                try:
                    filament_m = float(filament_m_raw)
                except ValueError:
                    flash(trans("flash_print_job_invalid_filament"), "danger")
                    return redirect(url_for("order_detail", order_id=order.id))
                if filament_m < 0:
                    flash(trans("flash_print_job_invalid_filament"), "danger")
                    return redirect(url_for("order_detail", order_id=order.id))

            filament_g = None
            if filament_g_raw:
                try:
                    filament_g = float(filament_g_raw)
                except ValueError:
                    flash(trans("flash_print_job_invalid_filament"), "danger")
                    return redirect(url_for("order_detail", order_id=order.id))
                if filament_g < 0:
                    flash(trans("flash_print_job_invalid_filament"), "danger")
                    return redirect(url_for("order_detail", order_id=order.id))

            try:
                quantity = max(1, int(quantity_raw or "1"))
            except ValueError:
                quantity = 1

            valid_statuses = set(PRINT_JOB_STATUS_VALUES)
            status = status_raw if status_raw in valid_statuses else (job.status or "upload")
            previous_status = job.status
            if status == "started" and previous_status != "started":
                started_at = current_print_start_time()

            def _select_profile_id(model, raw_id, current_id):
                if raw_id in (None, "", "null"):
                    return None
                try:
                    raw_int = int(raw_id)
                except ValueError:
                    return current_id
                entry = model.query.filter_by(id=raw_int).first()
                if not entry:
                    return current_id
                if not entry.active and raw_int != current_id:
                    return current_id
                return entry.id

            job.printer_profile_id = _select_profile_id(
                PrinterProfile,
                printer_profile_id,
                job.printer_profile_id,
            )
            job.filament_material_id = _select_profile_id(
                FilamentMaterial,
                filament_material_id,
                job.filament_material_id,
            )

            job.note = note or None
            job.status = status
            job.started_at = started_at
            job.duration_min = duration_min
            job.filament_m = filament_m
            job.filament_g = filament_g
            job.quantity = quantity

            previous_status = order.status
            sync_3d_order_status_from_print_jobs(order)

            db.session.commit()
            _send_relevant_order_status_email(app, order, previous_status, get_status_context(trans).get("order_status_labels", {}))
            flash(trans("flash_print_job_updated"), "success")
            return redirect(url_for("order_detail", order_id=order.id))

        elif action == "delete_print_job":
            if current_user.role not in {"admin", "worker"} or not is_3d_print_order(order):
                abort(403)

            try:
                job_id = int(request.form.get("print_job_id", "0"))
            except ValueError:
                job_id = 0

            if not job_id:
                flash(trans("flash_print_job_invalid_id"), "danger")
                return redirect(url_for("order_detail", order_id=order.id))

            job = OrderPrintJob.query.filter_by(
                id=job_id,
                order_id=order.id,
            ).first()

            if not job:
                flash(trans("flash_print_job_not_found"), "warning")
                return redirect(url_for("order_detail", order_id=order.id))

            previous_status = order.status
            order_folder = Path(app.config["GCODE_UPLOAD_FOLDER"]) / f"order_{order.id}"
            full_path = order_folder / job.stored_name
            if full_path.exists():
                try:
                    full_path.unlink()
                except OSError:
                    app.logger.warning(
                        f"[order_detail] Could not delete gcode file on disk: {full_path}"
                    )

            db.session.delete(job)
            db.session.flush()
            sync_3d_order_status_from_print_jobs(order)
            db.session.commit()
            _send_relevant_order_status_email(app, order, previous_status, get_status_context(trans).get("order_status_labels", {}))
            flash(trans("flash_print_job_deleted"), "info")
            return redirect(url_for("order_detail", order_id=order.id))

        # --- 8) Datei l├Âschen ----------------------------------------------
        elif action == "delete_file":
            try:
                file_id = int(request.form.get("file_id", "0"))
            except ValueError:
                file_id = 0

            if not file_id:
                flash(trans("flash_invalid_file_id"), "danger")
                return redirect(url_for("order_detail", order_id=order.id))

            order_file = OrderFile.query.filter_by(
                id=file_id,
                order_id=order.id
            ).first()

            if not order_file:
                flash(trans("flash_file_not_found"), "warning")
                return redirect(url_for("order_detail", order_id=order.id))

            # Physische Datei l├Âschen
            order_folder = Path(app.config["UPLOAD_FOLDER"]) / f"order_{order.id}"
            full_path = order_folder / order_file.stored_name

            if full_path.exists():
                try:
                    full_path.unlink()
                except OSError:
                    app.logger.warning(
                        f"[order_detail] Could not delete file on disk: {full_path}"
                    )

            thumb_folder = order_folder / "thumbnails"
            thumb_names = set()
            if order_file.thumb_sm_path:
                thumb_names.add(order_file.thumb_sm_path)
            if order_file.thumb_lg_path:
                thumb_names.add(order_file.thumb_lg_path)
            if order_file.file_type and order_file.file_type.lower() == "stl":
                default_sm, default_lg = _build_model_thumbnail_names(order_file.stored_name)
                thumb_names.add(default_sm)
                thumb_names.add(default_lg)

            for name in thumb_names:
                thumb_path = thumb_folder / name
                if thumb_path.exists():
                    try:
                        thumb_path.unlink()
                    except OSError:
                        app.logger.warning(
                            f"[order_detail] Could not delete thumbnail on disk: {thumb_path}"
                        )

            # DB-Eintrag l├Âschen
            db.session.delete(order_file)
            db.session.commit()

            app.logger.debug(
                f"[order_detail] Deleted file {file_id} for order {order.id}"
            )

            flash(trans("flash_file_deleted"), "info")
            return redirect(url_for("order_detail", order_id=order.id))

        # --- 7) Projektbild l├Âschen ----------------------------------------
        elif action == "delete_image":
            try:
                image_id = int(request.form.get("image_id", "0"))
            except ValueError:
                image_id = 0

            if not image_id:
                flash(trans("flash_invalid_image_id"), "danger")
                return redirect(url_for("order_detail", order_id=order.id))

            image_entry = OrderImage.query.filter_by(
                id=image_id,
                order_id=order.id
            ).first()

            if not image_entry:
                flash(trans("flash_image_not_found"), "warning")
                return redirect(url_for("order_detail", order_id=order.id))

            image_folder = Path(app.config["IMAGE_UPLOAD_FOLDER"]) / f"order_{order.id}"
            full_path = image_folder / image_entry.stored_name

            if full_path.exists():
                try:
                    full_path.unlink()
                except OSError:
                    app.logger.warning(f"[order_detail] Could not delete image on disk: {full_path}")

            thumb_path = image_folder / "thumbnails" / image_entry.stored_name
            if thumb_path.exists():
                try:
                    thumb_path.unlink()
                except OSError:
                    app.logger.warning(f"[order_detail] Could not delete thumbnail on disk: {thumb_path}")

            db.session.delete(image_entry)
            db.session.commit()

            flash(trans("flash_image_deleted"), "info")
            return redirect(url_for("order_detail", order_id=order.id))

        # --- Projektvideo loeschen ------------------------------------------
        elif action == "delete_video":
            try:
                video_id = int(request.form.get("video_id", "0"))
            except ValueError:
                video_id = 0

            video_entry = OrderVideo.query.filter_by(
                id=video_id,
                order_id=order.id,
            ).first()
            if not video_entry:
                flash(trans("flash_video_not_found"), "warning")
                return order_detail_redirect("files")

            video_folder = Path(app.config["VIDEO_UPLOAD_FOLDER"]) / f"order_{order.id}"
            full_path = video_folder / video_entry.stored_name
            if full_path.exists():
                try:
                    full_path.unlink()
                except OSError:
                    app.logger.warning("[order_detail] Could not delete video on disk: %s", full_path)

            db.session.delete(video_entry)
            db.session.commit()
            flash(trans("flash_video_deleted"), "info")
            return order_detail_redirect("files")

    # --- Ungelesene Nachrichten vor Read-Update pruefen ---------------------
    read_status = OrderReadStatus.query.filter_by(
        order_id=order.id,
        user_id=current_user.id,
    ).first()

    previous_last_read = read_status.last_read_at if read_status else None
    latest_message_at = (
        db.session.query(func.max(OrderMessage.created_at))
        .filter(OrderMessage.order_id == order.id)
        .scalar()
    )
    expand_chat_panel = bool(
        latest_message_at and (previous_last_read is None or latest_message_at > previous_last_read)
    )

    # --- Lese-Status aktualisieren (GET + nach POST-Redirect) --------------
    now = datetime.utcnow()

    if read_status is None:
        read_status = OrderReadStatus(
            order_id=order.id,
            user_id=current_user.id,
            last_read_at=now,
        )
        db.session.add(read_status)
        app.logger.debug(
            f"[order_detail] Created new read status for order={order.id}, user={current_user.email}"
        )
    else:
        read_status.last_read_at = now
        app.logger.debug(
            f"[order_detail] Updated read status for order={order.id}, user={current_user.email}"
        )

    db.session.commit()

    # Zus├ñtzlich in Session merken (pro User, pro Order)
    session_key = f"order_last_read_{order.id}"
    session[session_key] = now.isoformat()
    app.logger.debug(
        f"[order_detail] Session last_read set for order={order.id}, key={session_key}, value={session[session_key]}"
    )

    messages = order.messages

    # Stammdaten f├╝r Auswahlfelder laden
    materials = Material.query.order_by(Material.name.asc()).all()
    colors = Color.query.order_by(Color.name.asc()).all()
    order_areas = OrderArea.query.order_by(OrderArea.name.asc()).all()
    cost_centers = CostCenter.query.filter_by(is_active=True).order_by(CostCenter.name.asc()).all()
    printer_profiles = PrinterProfile.query.filter_by(active=True).order_by(PrinterProfile.name.asc()).all()
    filament_materials = FilamentMaterial.query.filter_by(active=True).order_by(FilamentMaterial.name.asc()).all()

    if order.printer_profile_id and not any(
        profile.id == order.printer_profile_id for profile in printer_profiles
    ):
        selected_profile = PrinterProfile.query.get(order.printer_profile_id)
        if selected_profile:
            printer_profiles.append(selected_profile)
            printer_profiles.sort(key=lambda profile: (profile.name or "").lower())

    if order.filament_material_id and not any(
        material.id == order.filament_material_id for material in filament_materials
    ):
        selected_material = FilamentMaterial.query.get(order.filament_material_id)
        if selected_material:
            filament_materials.append(selected_material)
            filament_materials.sort(key=lambda material: (material.name or "").lower())

    print_jobs = []
    if is_3d_print_order(order):
        print_jobs = (
            OrderPrintJob.query
            .filter_by(order_id=order.id)
            .order_by(OrderPrintJob.uploaded_at.desc())
            .all()
        )
    selected_printer_profile_ids = {
        job.printer_profile_id for job in print_jobs if job.printer_profile_id
    }
    selected_filament_material_ids = {
        job.filament_material_id for job in print_jobs if job.filament_material_id
    }
    for profile_id in selected_printer_profile_ids:
        if not any(profile.id == profile_id for profile in printer_profiles):
            selected_profile = PrinterProfile.query.get(profile_id)
            if selected_profile:
                printer_profiles.append(selected_profile)
    printer_profiles.sort(key=lambda profile: (profile.name or "").lower())

    for material_id in selected_filament_material_ids:
        if not any(material.id == material_id for material in filament_materials):
            selected_material = FilamentMaterial.query.get(material_id)
            if selected_material:
                filament_materials.append(selected_material)
    filament_materials.sort(key=lambda material: (material.name or "").lower())

    gcode_folder = Path(app.config["GCODE_UPLOAD_FOLDER"]) / f"order_{order.id}"
    metadata_changed = False
    for job in print_jobs:
        if job.stored_name:
            metadata_changed = apply_gcode_metadata_to_job(job, gcode_folder / job.stored_name) or metadata_changed
    if metadata_changed:
        db.session.commit()

    poster_files = []
    if is_plotter_order(order):
        poster_files = (
            OrderPosterFile.query
            .filter_by(order_id=order.id)
            .order_by(OrderPosterFile.uploaded_at.desc())
            .all()
        )
        poster_thumbnail_changed = False
        for poster in poster_files:
            before = poster.thumb_path
            if ensure_poster_thumbnail_file(order, poster) and poster.thumb_path != before:
                poster_thumbnail_changed = True
        if poster_thumbnail_changed:
            db.session.commit()

    procurement_articles = []
    procurement_article_position_count = 0
    procurement_article_total_price = 0.0
    email_favorites = (
        UserEmailFavorite.query
        .filter_by(user_id=current_user.id)
        .order_by(UserEmailFavorite.email.asc())
        .all()
    )
    if is_procurement_order(order):
        procurement_articles = (
            OrderProcurementArticle.query
            .filter_by(order_id=order.id)
            .order_by(OrderProcurementArticle.position_number.asc(), OrderProcurementArticle.created_at.asc(), OrderProcurementArticle.id.asc())
            .all()
        )
        if ensure_procurement_article_position_numbers(order.id):
            db.session.commit()
            procurement_articles = (
                OrderProcurementArticle.query
                .filter_by(order_id=order.id)
                .order_by(OrderProcurementArticle.position_number.asc(), OrderProcurementArticle.created_at.asc(), OrderProcurementArticle.id.asc())
                .all()
            )
        procurement_article_position_count = len(procurement_articles)
        procurement_article_total_price = sum(
            (article.price_per_unit_incl_vat or 0.0) * (article.quantity or 1)
            for article in procurement_articles
        )
    settings = load_app_settings(app)
    procurement_article_description_preview_chars = coerce_positive_int(
        settings.get("procurement_article_description_preview_chars"),
        DEFAULT_SETTINGS["procurement_article_description_preview_chars"],
    )

    status_context = get_status_context(inject_globals().get("t"))
    app.logger.debug(
        f"[order_detail] Render detail for order {order.id}: status={order.status!r}, "
        f"messages_count={len(messages)}, files_count={len(order.files)}"
    )
    return render_template(
        "order_detail.html",
        order=order,
        messages=messages,
        order_statuses=status_context["order_statuses"],
        materials=materials,
        colors=colors,
        order_areas=order_areas,
        cost_centers=cost_centers,
        printer_profiles=printer_profiles,
        filament_materials=filament_materials,
        print_jobs=print_jobs,
        poster_files=poster_files,
        procurement_articles=procurement_articles,
        procurement_article_position_count=procurement_article_position_count,
        procurement_article_total_price=procurement_article_total_price,
        email_favorites=email_favorites,
        procurement_article_description_preview_chars=procurement_article_description_preview_chars,
        print_job_statuses=status_context["print_job_statuses"],
        print_job_status_labels=status_context["print_job_status_labels"],
        print_job_status_styles=status_context["print_job_status_styles"],
        tags_value=order.tags_entry.tags if order.tags_entry else "",
        active_tab=active_tab,
        visible_tabs=visible_tabs,
        expand_chat_panel=expand_chat_panel,
    )


@app.route("/orders/<int:order_id>/messages-fragment")
@login_required
def order_messages_fragment(order_id):
    """
    Liefert nur den Nachrichten-Thread als HTML-Fragment fÃ¼r Auto-Refresh.
    """
    order = Order.query.get_or_404(order_id)

    # Access control wie in order_detail
    if not can_view_order(order, current_user):
        abort(403)

    messages = order.messages
    return render_template("order_messages_fragment.html", messages=messages)


@app.route("/orders/<int:order_id>/images/<int:image_id>/thumbnail")
@login_required
def order_image_thumbnail(order_id, image_id):
    order = Order.query.get_or_404(order_id)
    if not can_view_order(order, current_user):
        abort(403)

    image_entry = OrderImage.query.filter_by(id=image_id, order_id=order.id).first_or_404()

    thumb_folder = Path(app.config["IMAGE_UPLOAD_FOLDER"]) / f"order_{order.id}" / "thumbnails"
    thumb_path = thumb_folder / image_entry.stored_name

    if thumb_path.exists():
        return send_from_directory(
            directory=str(thumb_folder),
            path=image_entry.stored_name,
            as_attachment=False,
        )

    image_folder = Path(app.config["IMAGE_UPLOAD_FOLDER"]) / f"order_{order.id}"
    fallback_path = image_folder / image_entry.stored_name

    if fallback_path.exists():
        return send_from_directory(
            directory=str(image_folder),
            path=image_entry.stored_name,
            as_attachment=False,
        )

    abort(404)


@app.route("/orders/<int:order_id>/images/<int:image_id>/view")
@login_required
def order_image_view(order_id, image_id):
    order = Order.query.get_or_404(order_id)
    if not can_view_order(order, current_user):
        abort(403)

    image_entry = OrderImage.query.filter_by(id=image_id, order_id=order.id).first_or_404()

    image_folder = Path(app.config["IMAGE_UPLOAD_FOLDER"]) / f"order_{order.id}"
    image_path = image_folder / image_entry.stored_name

    if image_path.exists():
        return send_from_directory(
            directory=str(image_folder),
            path=image_entry.stored_name,
            as_attachment=False,
        )

    abort(404)


@app.route("/orders/<int:order_id>/files/<int:file_id>/thumbnail/<size>", methods=["GET", "POST"])
@login_required
def order_file_thumbnail(order_id, file_id, size):
    order = Order.query.get_or_404(order_id)
    if not can_view_order(order, current_user):
        abort(403)

    order_file = OrderFile.query.filter_by(id=file_id, order_id=order.id).first_or_404()
    if (order_file.file_type or "").lower() not in {"stl", "3mf"}:
        abort(404)
    if size not in {"sm", "lg"}:
        abort(404)

    order_folder = Path(app.config["UPLOAD_FOLDER"]) / f"order_{order.id}"
    thumb_folder = order_folder / "thumbnails"
    thumb_sm_name, thumb_lg_name = _build_model_thumbnail_names(order_file.stored_name)
    thumb_name = order_file.thumb_sm_path or thumb_sm_name
    if size == "lg":
        thumb_name = order_file.thumb_lg_path or thumb_lg_name

    if request.method == "POST":
        data = request.get_json(silent=True) or {}
        data_url = data.get("data_url") or request.form.get("data_url")
        image = None
        if "thumbnail" in request.files:
            try:
                image = Image.open(request.files["thumbnail"].stream)
            except Exception:
                image = None
        if image is None and data_url:
            image = _image_from_data_url(data_url)
        if image is None:
            return jsonify({"ok": False, "error": "invalid_image"}), 400

        thumb_sm_path = thumb_folder / thumb_sm_name
        thumb_lg_path = thumb_folder / thumb_lg_name
        small_ok, large_ok = save_model_thumbnail_from_image(image, thumb_sm_path, thumb_lg_path)
        order_file.thumb_sm_path = thumb_sm_name if small_ok else None
        order_file.thumb_lg_path = thumb_lg_name if large_ok else None
        order_file.has_3d_preview = True
        order_file.preview_status = "ok" if (small_ok or large_ok) else "failed"
        db.session.commit()

        if not (small_ok or large_ok):
            return jsonify({"ok": False, "error": "save_failed"}), 500

        return jsonify({"ok": True})

    thumb_path = thumb_folder / thumb_name
    if not thumb_path.exists():
        source_path = order_folder / order_file.stored_name
        if source_path.exists():
            update_order_file_preview(order_file, source_path)
            db.session.commit()
            thumb_name = order_file.thumb_sm_path or thumb_sm_name
            if size == "lg":
                thumb_name = order_file.thumb_lg_path or thumb_lg_name
            thumb_path = thumb_folder / thumb_name

    if thumb_path.exists():
        return send_from_directory(
            directory=str(thumb_folder),
            path=thumb_name,
            as_attachment=False,
        )

    abort(404)


@app.route("/orders/<int:order_id>/files/<int:file_id>/preview")
@login_required
def order_file_preview(order_id, file_id):
    order = Order.query.get_or_404(order_id)
    if not can_view_order(order, current_user):
        abort(403)

    order_file = OrderFile.query.filter_by(id=file_id, order_id=order.id).first_or_404()
    order_folder = Path(app.config["UPLOAD_FOLDER"]) / f"order_{order.id}"
    full_path = order_folder / order_file.stored_name

    if not full_path.exists():
        abort(404)

    mime = mimetypes.guess_type(order_file.original_name or order_file.stored_name)[0]
    if not mime:
        if (order_file.file_type or "").lower() == "stl":
            mime = "model/stl"
        elif (order_file.file_type or "").lower() == "3mf":
            mime = "model/3mf"
        else:
            mime = "application/octet-stream"

    return send_from_directory(
        directory=str(order_folder),
        path=order_file.stored_name,
        as_attachment=False,
        mimetype=mime,
    )


@app.route("/orders/<int:order_id>/images/<int:image_id>/download")
@login_required
def download_order_image(order_id, image_id):
    trans = inject_globals().get("t")
    order = Order.query.get_or_404(order_id)
    if not can_view_order(order, current_user):
        abort(403)

    image_entry = OrderImage.query.filter_by(id=image_id, order_id=order.id).first_or_404()

    image_folder = Path(app.config["IMAGE_UPLOAD_FOLDER"]) / f"order_{order.id}"
    full_path = image_folder / image_entry.stored_name

    if not full_path.exists():
        flash(trans("flash_image_missing_server"), "danger")
        return redirect(url_for("order_detail", order_id=order.id))

    return send_from_directory(
        directory=str(image_folder),
        path=image_entry.stored_name,
        as_attachment=True,
        download_name=image_entry.original_name,
    )


@app.route("/orders/<int:order_id>/videos/<int:video_id>/view")
@login_required
def order_video_view(order_id, video_id):
    order = Order.query.get_or_404(order_id)
    if not can_view_order(order, current_user):
        abort(403)

    video_entry = OrderVideo.query.filter_by(id=video_id, order_id=order.id).first_or_404()
    video_folder = Path(app.config["VIDEO_UPLOAD_FOLDER"]) / f"order_{order.id}"
    full_path = video_folder / video_entry.stored_name
    if not full_path.exists():
        abort(404)

    mime = mimetypes.guess_type(video_entry.original_name or video_entry.stored_name)[0]
    return send_from_directory(
        directory=str(video_folder),
        path=video_entry.stored_name,
        as_attachment=False,
        mimetype=mime,
        conditional=True,
    )


@app.route("/orders/<int:order_id>/videos/<int:video_id>/download")
@login_required
def download_order_video(order_id, video_id):
    trans = inject_globals().get("t")
    order = Order.query.get_or_404(order_id)
    if not can_view_order(order, current_user):
        abort(403)

    video_entry = OrderVideo.query.filter_by(id=video_id, order_id=order.id).first_or_404()
    video_folder = Path(app.config["VIDEO_UPLOAD_FOLDER"]) / f"order_{order.id}"
    full_path = video_folder / video_entry.stored_name
    if not full_path.exists():
        flash(trans("flash_video_missing_server"), "danger")
        return redirect(url_for("order_detail", order_id=order.id, tab="files"))

    return send_from_directory(
        directory=str(video_folder),
        path=video_entry.stored_name,
        as_attachment=True,
        download_name=video_entry.original_name,
    )

# ============================================================
# Datei-Download
# ============================================================

@app.route("/orders/<int:order_id>/files/<int:file_id>/download")
@login_required
def download_order_file(order_id, file_id):
    """
    Einfache Download-Route f├╝r eine Datei zu einem Auftrag.
    """
    trans = inject_globals().get("t")
    # Auftrag laden
    order = Order.query.get_or_404(order_id)

    # Access control wie in order_detail
    if not can_view_order(order, current_user):
        abort(403)

    # Datei suchen
    order_file = OrderFile.query.filter_by(
        id=file_id,
        order_id=order.id
    ).first_or_404()

    # Pfad zusammensetzen
    order_folder = Path(app.config["UPLOAD_FOLDER"]) / f"order_{order.id}"
    full_path = order_folder / order_file.stored_name

    if not full_path.exists():
        flash(trans("flash_file_missing_server"), "danger")
        return redirect(url_for("order_detail", order_id=order.id))

    # Download ausliefern
    return send_from_directory(
        directory=str(order_folder),
        path=order_file.stored_name,
        as_attachment=True,
        download_name=order_file.original_name,  # Name, den der User sieht
    )


@app.route("/orders/<int:order_id>/print-jobs/<int:job_id>/download")
@login_required
def download_print_job(order_id, job_id):
    trans = inject_globals().get("t")
    order = Order.query.get_or_404(order_id)

    if not can_view_order(order, current_user):
        abort(403)
    if not is_3d_print_order(order):
        abort(404)

    job = OrderPrintJob.query.filter_by(
        id=job_id,
        order_id=order.id,
    ).first_or_404()

    order_folder = Path(app.config["GCODE_UPLOAD_FOLDER"]) / f"order_{order.id}"
    full_path = order_folder / job.stored_name

    if not full_path.exists():
        flash(trans("flash_file_missing_server"), "danger")
        return redirect(url_for("order_detail", order_id=order.id))

    return send_from_directory(
        directory=str(order_folder),
        path=job.stored_name,
        as_attachment=True,
        download_name=job.original_name,
    )


@app.route("/orders/<int:order_id>/posters/<int:poster_id>/download")
@login_required
def download_poster_file(order_id, poster_id):
    trans = inject_globals().get("t")
    order = Order.query.get_or_404(order_id)

    if not can_view_order(order, current_user):
        abort(403)
    if not is_plotter_order(order):
        abort(404)

    poster = OrderPosterFile.query.filter_by(
        id=poster_id,
        order_id=order.id,
    ).first_or_404()

    order_folder = Path(app.config["POSTER_UPLOAD_FOLDER"]) / f"order_{order.id}"
    full_path = order_folder / poster.stored_name

    if not full_path.exists():
        flash(trans("flash_file_missing_server"), "danger")
        return redirect(url_for("order_detail", order_id=order.id, tab="posters"))

    return send_from_directory(
        directory=str(order_folder),
        path=poster.stored_name,
        as_attachment=True,
        download_name=poster.original_name,
    )


@app.route("/orders/<int:order_id>/procurement-articles/<int:article_id>/note/download")
@login_required
def download_procurement_article_note_file(order_id, article_id):
    trans = inject_globals().get("t")
    order = Order.query.get_or_404(order_id)

    if not can_view_order(order, current_user):
        abort(403)
    if not is_procurement_order(order):
        abort(404)

    article = OrderProcurementArticle.query.filter_by(
        id=article_id,
        order_id=order.id,
    ).first_or_404()

    if not article.note_file_stored_name:
        flash(trans("flash_procurement_note_file_missing"), "warning")
        return redirect(url_for("order_detail", order_id=order.id, tab="articles"))

    note_folder = Path(app.config["PROCUREMENT_NOTE_UPLOAD_FOLDER"]) / f"order_{order.id}"
    full_path = note_folder / article.note_file_stored_name

    if not full_path.exists():
        flash(trans("flash_file_missing_server"), "danger")
        return redirect(url_for("order_detail", order_id=order.id, tab="articles"))

    return send_from_directory(
        directory=str(note_folder),
        path=article.note_file_stored_name,
        as_attachment=True,
        download_name=article.note_file_original_name or article.note_file_stored_name,
    )


@app.route("/orders/<int:order_id>/posters/<int:poster_id>/thumbnail")
@login_required
def poster_file_thumbnail(order_id, poster_id):
    order = Order.query.get_or_404(order_id)

    if not can_view_order(order, current_user):
        abort(403)
    if not is_plotter_order(order):
        abort(404)

    poster = OrderPosterFile.query.filter_by(
        id=poster_id,
        order_id=order.id,
    ).first_or_404()
    if not ensure_poster_thumbnail_file(order, poster):
        abort(404)
    db.session.commit()

    thumb_folder = Path(app.config["POSTER_UPLOAD_FOLDER"]) / f"order_{order.id}" / "thumbnails"
    thumb_path = thumb_folder / poster.thumb_path
    if not thumb_path.exists():
        abort(404)

    return send_from_directory(
        directory=str(thumb_folder),
        path=poster.thumb_path,
        as_attachment=False,
        mimetype="image/png",
    )


@app.route("/files/<int:file_id>/set-color", methods=["POST"])
@login_required
def set_file_color(file_id):
    order_file = OrderFile.query.get_or_404(file_id)
    order = Order.query.get_or_404(order_file.order_id)

    if not can_view_order(order, current_user):
        abort(403)

    payload = request.get_json(silent=True) or request.form
    color_id_raw = payload.get("color_id") if payload else None

    if color_id_raw in (None, "", "null"):
        order_file.color_id = None
    else:
        try:
            color_id = int(color_id_raw)
        except (TypeError, ValueError):
            return jsonify({"ok": False, "error": "invalid_color_id"}), 400

        color = Color.query.get(color_id)
        if not color:
            return jsonify({"ok": False, "error": "color_not_found"}), 404
        order_file.color_id = color_id

    db.session.commit()
    return jsonify({"ok": True, "color_id": order_file.color_id})


# ============================================================
# Dashboard
# ============================================================

@app.route("/dashboard", methods=["GET", "POST"])
@login_required
def dashboard():
    """
    ├£bersicht aller Auftr├ñge (Admin: alle, User: nur eigene).
    Zeigt:
    - Status, Material, Farbe, Owner
    - "new message"-Badge
    - Anzahl Dateien ("Files") pro Auftrag
    """
    app.logger.debug(
        f"[dashboard] user={current_user.email}, role={current_user.role}"
    )
    trans = inject_globals().get("t")
    status_context = get_status_context(trans)
    sort_by = (request.args.get("sort") or "created").strip().lower()
    sort_dir = (request.args.get("dir") or "desc").strip().lower()
    if sort_by not in {"category", "area", "title", "status", "owner", "created"}:
        sort_by = "created"
    if sort_dir not in {"asc", "desc"}:
        sort_dir = "desc"
    settings = load_app_settings(app)
    dashboard_column_defs = {
        item["key"]: item
        for item in DASHBOARD_COLUMN_DEFS
    }
    dashboard_columns = [
        {
            **entry,
            "label": trans(dashboard_column_defs[entry["key"]]["label"]),
        }
        for entry in normalize_dashboard_columns(settings.get("dashboard_columns"))
        if entry["visible"]
    ]
    per_page_options = list(DASHBOARD_ROWS_PER_PAGE_OPTIONS)
    default_per_page = settings.get("dashboard_rows_per_page") or DEFAULT_SETTINGS["dashboard_rows_per_page"]
    if default_per_page not in per_page_options:
        default_per_page = DEFAULT_SETTINGS["dashboard_rows_per_page"]
    try:
        per_page = int(request.args.get("per_page") or default_per_page)
    except (TypeError, ValueError):
        per_page = default_per_page
    if per_page not in per_page_options:
        per_page = default_per_page
    try:
        page = int(request.args.get("page") or 1)
    except (TypeError, ValueError):
        page = 1
    page = max(page, 1)
    dashboard_filter_session_keys = {
        "category": "dashboard_filter_category",
        "area": "dashboard_filter_area",
        "status": "dashboard_filter_status",
    }

    def _get_persistent_dashboard_filter(name):
        session_key = dashboard_filter_session_keys[name]
        if name in request.args:
            value = (request.args.get(name) or "").strip()
            if value:
                session[session_key] = value
            else:
                session.pop(session_key, None)
            return value
        return (session.get(session_key) or "").strip()

    selected_category_id_raw = _get_persistent_dashboard_filter("category")
    selected_area_id_raw = _get_persistent_dashboard_filter("area")
    selected_status = _get_persistent_dashboard_filter("status")
    dashboard_search_query = (request.args.get("q") or "").strip()

    if request.method == "POST":
        action = (request.form.get("action") or "").strip()
        allowed_priorities = set(ANNOUNCEMENT_PRIORITY_META.keys())

        if action == "create_announcement":
            if current_user.role != "admin":
                abort(403)
            if not _consume_announcement_form_token():
                return _reject_duplicate_announcement_submission(url_for("dashboard"))
            title = (request.form.get("announcement_title") or "").strip()
            body = (request.form.get("announcement_body") or "").strip()
            priority = (request.form.get("announcement_priority") or "info").strip()
            if priority not in allowed_priorities:
                priority = "info"
            if not title or not body:
                flash(trans("flash_announcement_required"), "warning")
                return redirect(url_for("dashboard"))

            announcement = Announcement(
                title=title[:200],
                body=body,
                priority=priority,
                created_by_id=current_user.id,
                updated_by_id=current_user.id,
            )
            db.session.add(announcement)
            db.session.commit()
            if priority == "attention_email":
                send_announcement_attention_notification(app, announcement)
            flash(trans("flash_announcement_created"), "success")
            return redirect(url_for("dashboard"))

        if action == "update_announcement":
            if current_user.role != "admin":
                abort(403)
            if not _consume_announcement_form_token():
                return _reject_duplicate_announcement_submission(url_for("dashboard"))
            try:
                announcement_id = int(request.form.get("announcement_id", "0"))
            except ValueError:
                announcement_id = 0

            if not announcement_id:
                flash(trans("flash_announcement_not_found"), "warning")
                return redirect(url_for("dashboard"))

            announcement = Announcement.query.filter_by(id=announcement_id).first()
            if not announcement:
                flash(trans("flash_announcement_not_found"), "warning")
                return redirect(url_for("dashboard"))

            title = (request.form.get("announcement_title") or "").strip()
            body = (request.form.get("announcement_body") or "").strip()
            priority = (request.form.get("announcement_priority") or "info").strip()
            if priority not in allowed_priorities:
                priority = "info"
            if not title or not body:
                flash(trans("flash_announcement_required"), "warning")
                return redirect(url_for("dashboard"))

            announcement.title = title[:200]
            announcement.body = body
            announcement.priority = priority
            announcement.updated_by_id = current_user.id
            announcement.updated_at = datetime.utcnow()
            AnnouncementRead.query.filter_by(announcement_id=announcement.id).delete()
            db.session.commit()
            flash(trans("flash_announcement_updated"), "success")
            return redirect(url_for("dashboard"))

        if action == "mark_announcement_read":
            try:
                announcement_id = int(request.form.get("announcement_id", "0"))
            except ValueError:
                announcement_id = 0

            if not announcement_id:
                flash(trans("flash_announcement_not_found"), "warning")
                return redirect(url_for("dashboard"))

            announcement = Announcement.query.filter_by(id=announcement_id).first()
            if not announcement:
                flash(trans("flash_announcement_not_found"), "warning")
                return redirect(url_for("dashboard"))

            existing = AnnouncementRead.query.filter_by(
                announcement_id=announcement_id,
                user_id=current_user.id,
            ).first()
            if existing:
                existing.read_at = datetime.utcnow()
            else:
                db.session.add(
                    AnnouncementRead(
                        announcement_id=announcement_id,
                        user_id=current_user.id,
                    )
                )
            db.session.commit()
            flash(trans("flash_announcement_archived"), "info")
            return redirect(url_for("dashboard"))

    # 1) Orders laden (je nach Rolle)
    if current_user.role == "admin":
        orders = (
            Order.query
            .filter(Order.is_archived.is_(False))
            .order_by(Order.created_at.desc())
            .all()
        )
    else:
        managed_category_ids = {
            permission.category_id
            for permission in UserOrderCategoryPermission.query.filter_by(
                user_id=current_user.id,
                can_manage=True,
            ).all()
        }
        for category in OrderCategory.query.filter_by(active=True).all():
            if current_user.role in category.worker_roles():
                managed_category_ids.add(category.id)

        orders = (
            Order.query
            .filter(
                or_(
                    Order.user_id == current_user.id,
                    Order.category_id.in_(managed_category_ids) if managed_category_ids else False,
                )
            )
            .filter(Order.is_archived.is_(False))
            .order_by(Order.created_at.desc())
            .all()
        )

    if current_user.role in {"admin", "worker"}:
        visible_area_ids = {
            pref.area_id
            for pref in UserOrderAreaPreference.query.filter_by(user_id=current_user.id).all()
        }
        if visible_area_ids:
            orders = [order for order in orders if order.area_id in visible_area_ids]

    app.logger.debug(f"[dashboard] Loaded {len(orders)} orders")

    category_filters_map = {}
    area_filters_map = {}
    configured_status_keys = {
        key
        for key, _label in status_context.get("order_statuses", [])
        if key
    }
    status_filter_values = set(configured_status_keys)
    for order in orders:
        category = get_order_category(order)
        if category and category.id is not None:
            category_filters_map[category.id] = category.name
        if order.area and order.area.id is not None:
            area_filters_map[order.area.id] = order.area.name
        if order.status:
            status_filter_values.add(order.status)

    category_filters = [
        {"id": category_id, "name": category_name}
        for category_id, category_name in sorted(
            category_filters_map.items(),
            key=lambda item: (item[1] or "").lower(),
        )
    ]
    area_filters = [
        {"id": area_id, "name": area_name}
        for area_id, area_name in sorted(
            area_filters_map.items(),
            key=lambda item: (item[1] or "").lower(),
        )
    ]
    status_filters = sorted(
        status_filter_values,
        key=lambda value: (
            status_context["order_status_labels"].get(value, value) or ""
        ).lower(),
    )

    selected_category_id = None
    if selected_category_id_raw:
        try:
            selected_category_id = int(selected_category_id_raw)
        except (TypeError, ValueError):
            selected_category_id = None
            session.pop(dashboard_filter_session_keys["category"], None)

    selected_area_id = None
    if selected_area_id_raw:
        try:
            selected_area_id = int(selected_area_id_raw)
        except (TypeError, ValueError):
            selected_area_id = None
            session.pop(dashboard_filter_session_keys["area"], None)

    category_filter_ids = {item["id"] for item in category_filters}
    if selected_category_id is not None and selected_category_id not in category_filter_ids:
        selected_category_id = None
        session.pop(dashboard_filter_session_keys["category"], None)

    area_filter_ids = {item["id"] for item in area_filters}
    if selected_area_id is not None and selected_area_id not in area_filter_ids:
        selected_area_id = None
        session.pop(dashboard_filter_session_keys["area"], None)

    if selected_status and selected_status not in status_filter_values:
        selected_status = ""
        session.pop(dashboard_filter_session_keys["status"], None)

    if selected_category_id is not None:
        orders = [order for order in orders if order.category_id == selected_category_id]
    if selected_area_id is not None:
        orders = [order for order in orders if order.area_id == selected_area_id]
    if selected_status:
        orders = [order for order in orders if (order.status or "") == selected_status]
    if dashboard_search_query:
        search_term = dashboard_search_query.lower()

        def _dashboard_search_values(order):
            created_at = order.created_at
            created_values = []
            if created_at:
                created_values = [
                    created_at.strftime("%Y-%m-%d"),
                    created_at.strftime("%d.%m.%Y"),
                    created_at.strftime("%Y-%m-%d %H:%M"),
                    created_at.strftime("%d.%m.%Y %H:%M"),
                ]
            display_title = f"#{order.id}-{order.title or ''}"
            return [
                str(order.id),
                f"#{order.id}",
                display_title,
                order.title or "",
                order.description or "",
                order.user.email if order.user else "",
                *created_values,
            ]

        orders = [
            order
            for order in orders
            if any(search_term in value.lower() for value in _dashboard_search_values(order))
        ]

    def _dashboard_sort_value(order):
        if sort_by == "category":
            category = get_order_category(order)
            return ((category.name if category else "") or "").lower()
        if sort_by == "area":
            return ((order.area.name if order.area else "") or "").lower()
        if sort_by == "title":
            return (order.title or "").lower()
        if sort_by == "status":
            return (status_context["order_status_labels"].get(order.status, order.status) or "").lower()
        if sort_by == "owner":
            return ((order.user.email if order.user else "") or "").lower()
        if sort_by == "created":
            return order.created_at or datetime.min
        return order.created_at or datetime.min

    orders.sort(key=_dashboard_sort_value, reverse=(sort_dir == "desc"))

    total_orders = len(orders)
    total_pages = max(1, math.ceil(total_orders / per_page))
    if page > total_pages:
        page = total_pages
    page_start = (page - 1) * per_page
    page_end = page_start + per_page
    paginated_orders = orders[page_start:page_end]

    order_ids = [o.id for o in paginated_orders]
    plotter_order_ids = [o.id for o in paginated_orders if is_plotter_order(o)]
    procurement_order_ids = [o.id for o in paginated_orders if is_procurement_order(o)]
    print_order_ids = [
        o.id for o in paginated_orders
        if not is_plotter_order(o) and not is_procurement_order(o)
    ]
    for o in paginated_orders:
        app.logger.debug(
            f"[dashboard] Order id={o.id}, title={o.title!r}, status={o.status!r}"
        )

    # 2) Anzahl Dateien pro Order ermitteln
    file_counts = {}
    if print_order_ids:
        file_count_rows = (
            db.session.query(
                OrderFile.order_id,
                func.count(OrderFile.id)
            )
            .filter(OrderFile.order_id.in_(print_order_ids))
            .group_by(OrderFile.order_id)
            .all()
        )
        file_counts = {order_id: count for order_id, count in file_count_rows}
    if plotter_order_ids:
        poster_count_rows = (
            db.session.query(
                OrderPosterFile.order_id,
                func.count(OrderPosterFile.id)
            )
            .filter(OrderPosterFile.order_id.in_(plotter_order_ids))
            .group_by(OrderPosterFile.order_id)
            .all()
        )
        file_counts.update({order_id: count for order_id, count in poster_count_rows})
    if procurement_order_ids:
        procurement_count_rows = (
            db.session.query(
                OrderProcurementArticle.order_id,
                func.count(OrderProcurementArticle.id)
            )
            .filter(OrderProcurementArticle.order_id.in_(procurement_order_ids))
            .group_by(OrderProcurementArticle.order_id)
            .all()
        )
        file_counts.update({order_id: count for order_id, count in procurement_count_rows})

    app.logger.debug(f"[dashboard] file_counts: {file_counts}")

    print_job_counts = {}
    if print_order_ids:
        print_job_rows = (
            db.session.query(
                OrderPrintJob.order_id,
                OrderPrintJob.status,
                func.count(OrderPrintJob.id),
            )
            .filter(OrderPrintJob.order_id.in_(print_order_ids))
            .group_by(OrderPrintJob.order_id, OrderPrintJob.status)
            .all()
        )
        for order_id, status, count in print_job_rows:
            summary = print_job_counts.setdefault(
                order_id,
                {"total": 0, "started": 0, "finished": 0, "error": 0},
            )
            summary["total"] += count
            if status in ("started", "finished", "error"):
                summary[status] += count

    app.logger.debug(f"[dashboard] print_job_counts: {print_job_counts}")

    # 3) Latest message per order (Zeitstempel der letzten Nachricht)
    latest_messages = (
        db.session.query(
            OrderMessage.order_id,
            func.max(OrderMessage.created_at).label("latest_created"),
        )
        .filter(OrderMessage.order_id.in_(order_ids))
        .group_by(OrderMessage.order_id)
        .all()
    )
    latest_by_order = {order_id: latest_created for order_id, latest_created in latest_messages}
    app.logger.debug(f"[dashboard] latest_by_order: {latest_by_order}")

    # 4) Persistente Read-Zeitpunkte aus der Datenbank holen (pro Order)
    read_by_order = {}
    if order_ids:
        read_rows = (
            OrderReadStatus.query
            .filter(
                OrderReadStatus.user_id == current_user.id,
                OrderReadStatus.order_id.in_(order_ids),
            )
            .all()
        )
        read_by_order = {entry.order_id: entry.last_read_at for entry in read_rows}

    app.logger.debug(f"[dashboard] read_by_order (database): {read_by_order}")

    # 5) "last_new_message" pro Order berechnen (f├╝r "new message"-Badge)
    last_new_message = {}
    for o in paginated_orders:
        latest = latest_by_order.get(o.id)      # datetime oder None
        last_read = read_by_order.get(o.id)     # datetime oder None

        if latest is None:
            last_new_message[o.id] = None
        else:
            if last_read is None or latest > last_read:
                last_new_message[o.id] = latest
            else:
                last_new_message[o.id] = None

        app.logger.debug(
            f"[dashboard] Computed last_new_message for order {o.id}: {last_new_message[o.id]!r}"
        )

    announcements = Announcement.query.order_by(Announcement.created_at.desc()).all()
    announcement_reads = AnnouncementRead.query.filter_by(user_id=current_user.id).all()
    read_by_announcement = {entry.announcement_id: entry for entry in announcement_reads}
    announcements_unread = [a for a in announcements if a.id not in read_by_announcement]
    announcements_read = [a for a in announcements if a.id in read_by_announcement]

    return render_template(
        "dashboard.html",
        orders=paginated_orders,
        last_new_message=last_new_message,
        status_labels=status_context["order_status_labels"],
        status_styles=status_context["order_status_styles"],
        file_counts=file_counts,
        print_job_counts=print_job_counts,
        plotter_order_ids=set(plotter_order_ids),
        announcements_unread=announcements_unread,
        announcements_read=announcements_read,
        announcement_reads=read_by_announcement,
        announcement_priority_meta=ANNOUNCEMENT_PRIORITY_META,
        announcement_form_token=_new_announcement_form_token() if current_user.role == "admin" else "",
        sort_by=sort_by,
        sort_dir=sort_dir,
        page=page,
        per_page=per_page,
        per_page_options=per_page_options,
        dashboard_columns=dashboard_columns,
        category_filters=category_filters,
        area_filters=area_filters,
        status_filters=status_filters,
        selected_category_id=selected_category_id,
        selected_area_id=selected_area_id,
        selected_status=selected_status,
        dashboard_search_query=dashboard_search_query,
        total_orders=total_orders,
        total_pages=total_pages,
        page_start=page_start + 1 if total_orders else 0,
        page_end=min(page_end, total_orders),
    )


@app.route("/announcements/update", methods=["POST"])
@login_required
def announcement_update():
    trans = inject_globals().get("t")
    if current_user.role != "admin":
        abort(403)
    if not _consume_announcement_form_token():
        return _reject_duplicate_announcement_submission()

    try:
        announcement_id = int(request.form.get("announcement_id", "0"))
    except ValueError:
        announcement_id = 0

    if not announcement_id:
        flash(trans("flash_announcement_not_found"), "warning")
        return redirect(request.form.get("next") or url_for("dashboard"))

    announcement = Announcement.query.filter_by(id=announcement_id).first()
    if not announcement:
        flash(trans("flash_announcement_not_found"), "warning")
        return redirect(request.form.get("next") or url_for("dashboard"))

    title = (request.form.get("announcement_title") or "").strip()
    body = (request.form.get("announcement_body") or "").strip()
    priority = (request.form.get("announcement_priority") or "info").strip()
    if priority not in ANNOUNCEMENT_PRIORITY_META:
        priority = "info"
    if not title or not body:
        flash(trans("flash_announcement_required"), "warning")
        return redirect(request.form.get("next") or url_for("dashboard"))

    announcement.title = title[:200]
    announcement.body = body
    announcement.priority = priority
    announcement.updated_by_id = current_user.id
    announcement.updated_at = datetime.utcnow()
    AnnouncementRead.query.filter_by(announcement_id=announcement.id).delete()
    db.session.commit()

    flash(trans("flash_announcement_updated"), "success")
    return redirect(request.form.get("next") or url_for("dashboard"))



# ============================================================
# Logout
# ============================================================

@app.route("/logout")
@login_required
def logout():
    write_audit_log(app, "user_logout", user=current_user)
    logout_user()
    session.clear()
    trans = inject_globals().get("t")
    flash(trans("flash_logged_out"), "info")
    return redirect(url_for("landing"))


# ============================================================
# Admin: PDF-Export für Orders
# ============================================================

def _pdf_escape(text_value: str) -> str:
    """
    Escape f├╝r einfache PDF-Strings.
    """
    text_value = (text_value or "").replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    # PDFDocEncoding ist grob Latin-1; wir ersetzen nicht darstellbare Zeichen.
    return text_value.encode("latin-1", "replace").decode("latin-1")


def build_order_context(order, translator) -> dict:
    def fmt_dt(dt):
        return format_local_datetime(dt) if dt else ""

    def image_thumb_data_uri(image_entry: OrderImage) -> str:
        """
        Resolve a thumbnail (fallback to original) as data URI for PDF rendering.
        Generates the thumbnail on demand if it does not yet exist.
        """
        base_folder = Path(app.config["IMAGE_UPLOAD_FOLDER"]) / f"order_{order.id}"
        original_path = base_folder / image_entry.stored_name
        thumb_path = base_folder / "thumbnails" / image_entry.stored_name

        if thumb_path.exists():
            chosen = thumb_path
        elif original_path.exists():
            # create thumbnail if missing; ignore failures silently
            save_image_thumbnail(original_path, thumb_path)
            chosen = thumb_path if thumb_path.exists() else original_path
        else:
            chosen = None

        if not chosen or not chosen.exists():
            return ""

        mime, _ = mimetypes.guess_type(chosen.name)
        if not mime:
            mime = "image/png"
        try:
            data = base64.b64encode(chosen.read_bytes()).decode("ascii")
            return f"data:{mime};base64,{data}"
        except Exception as exc:  # noqa: BLE001
            app.logger.warning("Could not embed thumbnail for PDF (%s): %s", chosen, exc)
            return ""

    def model_thumb_data_uri(file_entry: OrderFile) -> str:
        if (file_entry.file_type or "").lower() != "stl":
            return ""

        base_folder = Path(app.config["UPLOAD_FOLDER"]) / f"order_{order.id}"
        original_path = base_folder / file_entry.stored_name
        thumb_folder = base_folder / "thumbnails"
        thumb_sm_name, thumb_lg_name = _build_model_thumbnail_names(file_entry.stored_name)

        candidates = []
        if file_entry.thumb_sm_path:
            candidates.append(thumb_folder / file_entry.thumb_sm_path)
        if file_entry.thumb_lg_path:
            candidates.append(thumb_folder / file_entry.thumb_lg_path)
        candidates.append(thumb_folder / thumb_sm_name)
        candidates.append(thumb_folder / thumb_lg_name)

        chosen = next((path for path in candidates if path.exists()), None)

        if not chosen and original_path.exists():
            generate_stl_thumbnails(original_path, thumb_folder / thumb_sm_name, thumb_folder / thumb_lg_name)
            if (thumb_folder / thumb_sm_name).exists():
                chosen = thumb_folder / thumb_sm_name
            elif (thumb_folder / thumb_lg_name).exists():
                chosen = thumb_folder / thumb_lg_name

        if not chosen or not chosen.exists():
            return ""

        mime, _ = mimetypes.guess_type(chosen.name)
        if not mime:
            mime = "image/png"
        try:
            data = base64.b64encode(chosen.read_bytes()).decode("ascii")
            return f"data:{mime};base64,{data}"
        except Exception as exc:  # noqa: BLE001
            app.logger.warning("Could not embed model thumbnail for PDF (%s): %s", chosen, exc)
            return ""

    def poster_thumb_data_uri(poster_entry: OrderPosterFile) -> str:
        base_folder = Path(app.config["POSTER_UPLOAD_FOLDER"]) / f"order_{order.id}"
        original_path = base_folder / poster_entry.stored_name
        thumb_path = base_folder / "thumbnails" / poster_entry.thumb_path if poster_entry.thumb_path else None

        if thumb_path and thumb_path.exists():
            chosen = thumb_path
        elif original_path.exists() and ensure_poster_thumbnail_file(order, poster_entry):
            thumb_path = base_folder / "thumbnails" / poster_entry.thumb_path if poster_entry.thumb_path else None
            chosen = thumb_path if thumb_path and thumb_path.exists() else original_path
        elif original_path.exists():
            chosen = original_path
        else:
            chosen = None

        if not chosen or not chosen.exists():
            return ""

        mime, _ = mimetypes.guess_type(chosen.name)
        if not mime:
            mime = "image/png"
        try:
            data = base64.b64encode(chosen.read_bytes()).decode("ascii")
            return f"data:{mime};base64,{data}"
        except Exception as exc:  # noqa: BLE001
            app.logger.warning("Could not embed poster thumbnail for PDF (%s): %s", chosen, exc)
            return ""

    generated_at = fmt_dt(datetime.utcnow())
    status_context = get_status_context(translator)
    status_labels = status_context.get("order_status_labels", {})
    print_job_status_labels = status_context.get("print_job_status_labels", {})
    order_is_plotter = is_plotter_order(order)

    print_jobs = (
        OrderPrintJob.query
        .filter_by(order_id=order.id)
        .order_by(OrderPrintJob.uploaded_at.desc())
        .all()
    )
    poster_files = (
        OrderPosterFile.query
        .filter_by(order_id=order.id)
        .order_by(OrderPosterFile.uploaded_at.desc())
        .all()
        if order_is_plotter
        else []
    )

    return {
        "app_name": "NeoFab",
        "app_version": APP_VERSION,
        "pdf_generated_at": generated_at,
        "order": order,
        "order_is_plotter": order_is_plotter,
        "order_dict": {
            "id": order.id,
            "title": order.title,
            "status": status_labels.get(order.status, order.status),
            "owner": order.user.email if order.user else "",
            "salutation": order.user.salutation if order.user else "",
            "first_name": order.user.first_name if order.user else "",
            "last_name": order.user.last_name if order.user else "",
            "address": order.user.address if order.user else "",
            "position": order.user.position if order.user else "",
            "study_program": order.user.study_program if order.user else "",
            "cost_center": order.cost_center.name if order.cost_center else "",
            "created_at": fmt_dt(order.created_at),
            "updated_at": fmt_dt(order.updated_at),
            "description": order.description or "",
            "summary_short": order.summary_short or "",
            "summary_long": order.summary_long or "",
            "project_group": order.project_group or "",
            "project_purpose": order.project_purpose or "",
            "project_use_case": order.project_use_case or "",
            "learning_points": order.learning_points or "",
            "background_info": order.background_info or "",
            "project_url": order.project_url or "",
            "tags": order.tags_entry.tags if getattr(order, "tags_entry", None) else "",
            "public_allow_poster": order.public_allow_poster,
            "public_allow_web": order.public_allow_web,
            "public_allow_social": order.public_allow_social,
        },
        "messages": [
            {
                "author": msg.user.email if msg.user else "",
                "role": msg.user.role if msg.user else "",
                "created_at": fmt_dt(msg.created_at),
                "content": msg.content,
            }
            for msg in order.messages
        ],
        "files": [
            {
                "name": f.original_name,
                "file_type": (f.file_type or "").upper(),
                "filesize": f.filesize,
                "uploaded_at": fmt_dt(f.uploaded_at),
                "note": f.note or "",
                "quantity": f.quantity or 1,
                "material": f.material.name if f.material else "",
                "color": f.color.name if f.color else "",
                "thumb_data_uri": model_thumb_data_uri(f),
            }
            for f in order.files
        ],
        "images": [
            {
                "name": img.original_name,
                "filesize": img.filesize,
                "uploaded_at": fmt_dt(img.uploaded_at),
                "note": img.note or "",
                "thumb_data_uri": image_thumb_data_uri(img),
            }
            for img in order.images
        ],
        "print_jobs": [
            {
                "name": job.original_name,
                "filesize": job.filesize,
                "uploaded_at": fmt_dt(job.uploaded_at),
                "status": print_job_status_labels.get(job.status, job.status),
                "started_at": fmt_dt(job.started_at),
                "duration_min": job.duration_min,
                "filament_m": job.filament_m,
                "filament_g": job.filament_g,
                "quantity": job.quantity or 1,
                "note": job.note or "",
            }
            for job in print_jobs
        ],
        "poster_files": [
            {
                "name": poster.original_name,
                "file_type": (poster.file_type or "").upper(),
                "filesize": poster.filesize,
                "uploaded_at": fmt_dt(poster.uploaded_at),
                "note": poster.note or "",
                "quantity": poster.quantity or 1,
                "due_date": poster.due_date.strftime("%Y-%m-%d") if poster.due_date else "",
                "thumb_data_uri": poster_thumb_data_uri(poster),
            }
            for poster in poster_files
        ],
        "t": translator,
    }


def render_pdf_with_template(template_path: str, context: dict) -> bytes:
    if not XHTML2PDF_AVAILABLE:
        app.logger.info(
            "xhtml2pdf not available, skipping template-based PDF. Import error: %r",
            XHTML2PDF_IMPORT_ERR,
        )
        return b""

    if not template_path:
        app.logger.info("No PDF template path configured, skipping template-based PDF.")
        return b""

    tpl_path = Path(template_path)
    if not tpl_path.exists():
        app.logger.info("PDF template not found at %s, skipping template-based PDF.", tpl_path)
        return b""

    env = Environment(
        loader=FileSystemLoader(str(tpl_path.parent)),
        autoescape=select_autoescape(["html", "xml"]),
    )
    tpl = env.get_template(tpl_path.name)
    html = tpl.render(**context)

    result = BytesIO()
    pisa_status = pisa.CreatePDF(html, dest=result, encoding="utf-8")
    if pisa_status.err:
        app.logger.error("xhtml2pdf failed with %s errors, falling back.", pisa_status.err)
        return b""
    return result.getvalue()


def _build_text_rows_pdf(text_rows: List[str]) -> bytes:
    start_y = 820
    step = 18
    content_parts = ["BT", "/F1 12 Tf"]
    for idx, row in enumerate(text_rows):
        y = start_y - idx * step
        content_parts.append(f"1 0 0 1 72 {y} Tm")
        content_parts.append(f"({_pdf_escape(row)}) Tj")
    content_parts.append("ET")
    content_stream = "\n".join(content_parts).encode("latin-1")

    objects = []
    objects.append("1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n")
    objects.append("2 0 obj\n<< /Type /Pages /Count 1 /Kids [3 0 R] >>\nendobj\n")
    objects.append(
        "3 0 obj\n"
        "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] "
        "/Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>\n"
        "endobj\n"
    )
    objects.append(
        f"4 0 obj\n<< /Length {len(content_stream)} >>\nstream\n".encode("latin-1")
        + content_stream
        + b"\nendstream\nendobj\n"
    )
    objects.append("5 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj\n")

    pdf_parts: List[bytes] = [b"%PDF-1.4\n"]
    offsets = [0]
    current = len(pdf_parts[0])
    for obj in objects:
        chunk = obj if isinstance(obj, (bytes, bytearray)) else obj.encode("latin-1")
        offsets.append(current)
        pdf_parts.append(chunk)
        current += len(chunk)

    xref_start = current
    size = len(objects) + 1
    xref_lines = [b"xref\n", f"0 {size}\n".encode("latin-1")]
    xref_lines.append(b"0000000000 65535 f \n")
    for off in offsets[1:]:
        xref_lines.append(f"{off:010d} 00000 n \n".encode("latin-1"))
    trailer = (
        b"trailer\n<< /Size "
        + str(size).encode("latin-1")
        + b" /Root 1 0 R >>\nstartxref\n"
        + str(xref_start).encode("latin-1")
        + b"\n%%EOF"
    )
    pdf_parts.extend(xref_lines)
    pdf_parts.append(trailer)
    return b"".join(pdf_parts)


def _build_order_pdf(order, translator) -> bytes:
    """
    Baut ein minimalistisches PDF (A4) mit Auftragsdetails.
    """
    lines: List[Tuple[str, str]] = []
    add = lambda label, value: lines.append((label, value)) if value else None
    status_labels = get_status_context(translator).get("order_status_labels", {})

    add("NeoFab", f"Version {APP_VERSION}")
    add("", "")
    add("Order ID", f"#{order.id}")
    add(translator("order_title_label"), order.title)
    add(translator("order_status_label"), status_labels.get(order.status, order.status))
    add(translator("order_owner_label"), order.user.email if order.user else "")
    add(translator("order_cost_center_label"), order.cost_center.name if order.cost_center else "")
    add(translator("order_created_label"), fmt_dt(order.created_at))
    add(translator("order_updated_label"), fmt_dt(order.updated_at))
    add(translator("order_summary_short"), order.summary_short or "")
    add(translator("order_summary_long"), order.summary_long or "")
    add(translator("order_project_group"), order.project_group or "")
    add(translator("order_description_label"), order.description or "")
    add(translator("order_project_purpose"), order.project_purpose or "")
    add(translator("order_project_use_case"), order.project_use_case or "")
    add(translator("order_learning_points"), order.learning_points or "")
    add(translator("order_background_info"), order.background_info or "")
    add(translator("order_project_url"), order.project_url or "")
    add(translator("order_tags"), order.tags_entry.tags if getattr(order, "tags_entry", None) else "")
    add(translator("order_public_sharing"), "")
    add("ÔÇó " + translator("order_allow_poster"), translator("badge_yes") if order.public_allow_poster else translator("badge_no"))
    add("ÔÇó " + translator("order_allow_web"), translator("badge_yes") if order.public_allow_web else translator("badge_no"))
    add("ÔÇó " + translator("order_allow_social"), translator("badge_yes") if order.public_allow_social else translator("badge_no"))

    add("", "")
    add(translator("messages_header"), "")
    for msg in order.messages:
        meta = []
        if msg.created_at:
            meta.append(fmt_dt(msg.created_at))
        if msg.user:
            meta.append(msg.user.email)
        meta_str = " - ".join(meta)
        content = msg.content.replace("\r", " ").replace("\n", " ").strip()
        add(f"ÔÇó {meta_str}", content)

    if is_plotter_order(order):
        add("", "")
        add(translator("posters_header"), "")
        poster_files = (
            OrderPosterFile.query
            .filter_by(order_id=order.id)
            .order_by(OrderPosterFile.uploaded_at.desc())
            .all()
        )
        if not poster_files:
            add(translator("posters_none"), "")
        for poster in poster_files:
            parts = []
            if poster.file_type:
                parts.append(poster.file_type.upper())
            parts.append(f"{translator('posters_quantity_label')} {poster.quantity or 1}")
            if poster.due_date:
                parts.append(f"{translator('posters_due_date_label')} {poster.due_date.strftime('%Y-%m-%d')}")
            if poster.note:
                parts.append(poster.note)
            if poster.filesize:
                parts.append(f"{(poster.filesize / 1024):.1f} KB")
            if poster.uploaded_at:
                parts.append(fmt_dt(poster.uploaded_at))
            add(f"- {poster.original_name}", " | ".join(parts))

        add("", "")
        add(translator("images_header"), "")
        for img in order.images:
            meta = []
            if img.filesize:
                meta.append(f"{(img.filesize / 1024):.1f} KB")
            if img.uploaded_at:
                meta.append(fmt_dt(img.uploaded_at))
            add(f"- {img.original_name}", " | ".join(meta))

        text_rows: List[str] = []
        for label, value in lines:
            line = f"{label}: {value}".strip()
            text_rows.append(line)
        return _build_text_rows_pdf(text_rows)

    add("", "")
    add(translator("files_header"), "")
    for f in order.files:
        parts = []
        if f.file_type:
            parts.append(f.file_type.upper())
        qty = f.quantity or 1
        parts.append(f"qty {qty}")
        if f.material:
            parts.append(f"{translator('files_material_label')}: {f.material.name}")
        if f.color:
            parts.append(f"{translator('files_color_label')}: {f.color.name}")
        if f.note:
            parts.append(f.note)
        add(f"ÔÇó {f.original_name}", " | ".join(parts))

    add("", "")
    add(translator("print_jobs_header"), "")
    print_job_status_labels = get_status_context(translator).get("print_job_status_labels", {})
    print_jobs = (
        OrderPrintJob.query
        .filter_by(order_id=order.id)
        .order_by(OrderPrintJob.uploaded_at.desc())
        .all()
    )
    for job in print_jobs:
        parts = []
        status_label = print_job_status_labels.get(job.status, job.status or "")
        if status_label:
            parts.append(status_label)
        parts.append(f"{translator('print_jobs_table_quantity')} {job.quantity or 1}")
        if job.started_at:
            parts.append(
                f"{translator('print_jobs_table_started_at')} {fmt_dt(job.started_at)}"
            )
        if job.duration_min is not None:
            parts.append(
                f"{translator('print_jobs_table_duration')} {job.duration_min} {translator('print_jobs_unit_minutes')}"
            )
        filament_parts = []
        if job.filament_m is not None:
            filament_parts.append(f"{job.filament_m:g} m")
        if job.filament_g is not None:
            filament_parts.append(f"{job.filament_g:g} g")
        if filament_parts:
            parts.append(
                f"{translator('print_jobs_table_filament')} {' / '.join(filament_parts)}"
            )
        if job.note:
            parts.append(f"{translator('print_jobs_table_note')} {job.note}")
        meta = []
        if job.filesize:
            meta.append(f"{(job.filesize / 1024):.1f} KB")
        if job.uploaded_at:
            meta.append(fmt_dt(job.uploaded_at))
        if meta:
            parts.append(" | ".join(meta))
        add(f"- {job.original_name}", " | ".join(parts))

    add("", "")
    add(translator("images_header"), "")
    for img in order.images:
        meta = []
        if img.filesize:
            meta.append(f"{(img.filesize / 1024):.1f} KB")
        if img.uploaded_at:
            meta.append(fmt_dt(img.uploaded_at))
        add(f"ÔÇó {img.original_name}", " | ".join(meta))

    text_rows: List[str] = []
    for label, value in lines:
        line = f"{label}: {value}".strip()
        text_rows.append(line)

    start_y = 820
    step = 18
    content_parts = ["BT", "/F1 12 Tf"]
    for idx, row in enumerate(text_rows):
        y = start_y - idx * step
        content_parts.append(f"1 0 0 1 72 {y} Tm")
        content_parts.append(f"({_pdf_escape(row)}) Tj")
    content_parts.append("ET")
    content_stream = "\n".join(content_parts).encode("latin-1")

    objects = []
    objects.append("1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n")
    objects.append("2 0 obj\n<< /Type /Pages /Count 1 /Kids [3 0 R] >>\nendobj\n")
    objects.append(
        "3 0 obj\n"
        "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] "
        "/Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>\n"
        "endobj\n"
    )
    objects.append(
        f"4 0 obj\n<< /Length {len(content_stream)} >>\nstream\n".encode("latin-1")
        + content_stream
        + b"\nendstream\nendobj\n"
    )
    objects.append("5 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj\n")

    pdf_parts: List[bytes] = [b"%PDF-1.4\n"]
    offsets = [0]
    current = len(pdf_parts[0])
    for obj in objects:
        chunk = obj if isinstance(obj, (bytes, bytearray)) else obj.encode("latin-1")
        offsets.append(current)
        pdf_parts.append(chunk)
        current += len(chunk)

    xref_start = current
    size = len(objects) + 1
    xref_lines = [b"xref\n", f"0 {size}\n".encode("latin-1")]
    xref_lines.append(b"0000000000 65535 f \n")
    for off in offsets[1:]:
        xref_lines.append(f"{off:010d} 00000 n \n".encode("latin-1"))
    trailer = (
        b"trailer\n<< /Size "
        + str(size).encode("latin-1")
        + b" /Root 1 0 R >>\nstartxref\n"
        + str(xref_start).encode("latin-1")
        + b"\n%%EOF"
    )
    pdf_parts.extend(xref_lines)
    pdf_parts.append(trailer)
    return b"".join(pdf_parts)


@app.route("/admin/orders/<int:order_id>/pdf")
@roles_required("admin")
def admin_order_pdf(order_id):
    order = Order.query.get_or_404(order_id)
    trans = inject_globals().get("t")
    context = build_order_context(order, trans)

    pdf_bytes = b""
    try:
        pdf_bytes = render_pdf_with_template(PDF_TEMPLATE_PATH, context)
    except Exception:
        app.logger.exception("Rendering PDF from template failed, falling back to default PDF.")

    if not pdf_bytes:
        app.logger.info("Fallback to built-in PDF generator for order %s", order_id)
        pdf_bytes = _build_order_pdf(order, trans)

    filename = f"order_{order.id}.pdf"
    return app.response_class(
        pdf_bytes,
        mimetype="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


# ============================================================
# Dev-Start
# ============================================================

if __name__ == "__main__":
    app.run(debug=True)
