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
from datetime import datetime
from pathlib import Path
import base64
import mimetypes
import os
import logging
import json
import re
import smtplib
from urllib.parse import parse_qs, urlparse
from email.message import EmailMessage

from sqlalchemy import func, text

from markupsafe import Markup, escape

from flask import (
    Flask,
    render_template,
    redirect,
    url_for,
    request,
    flash,
    session,
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

from typing import List, Tuple
from io import BytesIO

from PIL import Image

from jinja2 import Environment, FileSystemLoader, select_autoescape, Template
from config import (
    DEFAULT_SETTINGS,
    SETTINGS_FILE,
    coerce_positive_int,
    load_app_settings,
    save_app_settings,
)
from auth_utils import (
    roles_required,
    register_session_timeout,
    SESSION_LAST_ACTIVE_KEY,
)
from routes import create_admin_blueprint
from models import (
    db,
    User,
    Order,
    OrderMessage,
    OrderReadStatus,
    OrderFile,
    OrderImage,
    OrderTag,
    Material,
    Color,
    CostCenter,
    TrainingVideo,
)

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

# Max width for generated thumbnails (px)
THUMBNAIL_MAX_WIDTH = 200

# ├£bersetzungen aus externer Struktur laden (Ordner i18n im Projekt-Root)
I18N_DIR = BASE_DIR.parent / "i18n"
DEFAULT_LANG = "en"
SUPPORTED_LANGS = ("en", "de", "fr")
_translations_cache = {}

# Optionaler PDF-Template-Pfad (HTML)
PDF_TEMPLATE_PATH = os.environ.get(
    "NEOFAB_PDF_TEMPLATE",
    str(BASE_DIR.parent / "doku" / "pdf_template.html"),
)


def load_language_file(lang: str) -> dict:
    """
    L├ñdt eine Sprachdatei (JSON) aus i18n/<lang>.json.
    Gibt ein leeres Dict zur├╝ck, falls nicht vorhanden/lesbar.
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
    Cached Zugriff auf ├£bersetzungen.
    """
    lang = (lang or DEFAULT_LANG).lower()
    if lang not in _translations_cache:
        _translations_cache[lang] = load_language_file(lang)
    return _translations_cache[lang]

# Maximal erlaubte Upload-Gr├Â├ƒe (z.B. 50 MB)
app.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024  # 50 MB

# Einfache Logging-Konfiguration
logging.basicConfig(level=logging.DEBUG)
app.logger.setLevel(logging.DEBUG)

# Auftrags-Status-Codes (interne Werte + Labels)
ORDER_STATUSES = [
    ("new", "New"),
    ("in_progress", "In progress"),
    ("on_hold", "On hold"),
    ("completed", "Completed"),
    ("cancelled", "Cancelled"),
]

# Mapping der Status-Codes zu lesbaren Labels
STATUS_LABELS = {value: label for value, label in ORDER_STATUSES}

# Abw├ñrtskompatibilit├ñt f├╝r alte deutsche Statuswerte
STATUS_LABELS.setdefault("neu", "New")
STATUS_LABELS.setdefault("in_bearbeitung", "In progress")
STATUS_LABELS.setdefault("abgeschlossen", "Completed")

# Secret Key & Datenbank-Config
app.config["SECRET_KEY"] = os.environ.get("NEOFAB_SECRET_KEY", "dev-secret-change-me")

# SQLite-DB im Projektverzeichnis (absoluter Pfad)
db_path = BASE_DIR / "neofab.db"
app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{db_path}"

app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

load_app_settings(app)


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

    return {
        "app_version": APP_VERSION,
        "status_labels": STATUS_LABELS,
        "current_language": current_language,
        "t": t,
    }


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
        if "note" not in cols:
            statements.append("ALTER TABLE order_files ADD COLUMN note VARCHAR(255)")
        if "quantity" not in cols:
            statements.append("ALTER TABLE order_files ADD COLUMN quantity INTEGER NOT NULL DEFAULT 1")

        for stmt in statements:
            db.session.execute(text(stmt))
        if statements:
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
        if "sort_order" not in cols:
            db.session.execute(text("ALTER TABLE training_videos ADD COLUMN sort_order INTEGER NOT NULL DEFAULT 0"))
            db.session.commit()
    except Exception:
        app.logger.exception("Failed to ensure training_videos table exists")


with app.app_context():
    ensure_order_file_columns()
    ensure_order_image_columns()
    ensure_training_videos_table()


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


def _collect_order_recipients(order: Order, include_owner: bool = False) -> list[str]:
    recipients: list[str] = []
    seen = set()

    admin_users = User.query.filter_by(role="admin").all()
    for user in admin_users:
        email = (user.email or "").strip()
        if not email:
            continue
        key = email.lower()
        if key in seen:
            continue
        recipients.append(email)
        seen.add(key)

    if include_owner and order.user:
        owner_email = (order.user.email or "").strip()
        if owner_email:
            key = owner_email.lower()
            if key not in seen:
                recipients.append(owner_email)
                seen.add(key)

    return recipients


def send_admin_order_notification(order: Order) -> bool:
    """
    Send a notification email to all admin users (plus order creator) for a newly created order.
    Never raises; returns True on success, False otherwise.
    """
    try:
        settings = load_app_settings(app, force_reload=True)
        smtp_host = settings.get("smtp_host")
        smtp_port = settings.get("smtp_port")
        smtp_use_tls = bool(settings.get("smtp_use_tls"))
        smtp_use_ssl = bool(settings.get("smtp_use_ssl"))
        smtp_user = settings.get("smtp_user")
        smtp_password = settings.get("smtp_password")
        smtp_from = settings.get("smtp_from_address")

        if not smtp_host or not smtp_port or not smtp_from:
            app.logger.info("SMTP not configured, skipping admin notification.")
            return False

        recipients = _collect_order_recipients(order, include_owner=True)
        if not recipients:
            app.logger.info("No recipients found, skipping admin notification.")
            return False

        try:
            order_url = url_for("order_detail", order_id=order.id, _external=True)
        except Exception:
            order_url = url_for("order_detail", order_id=order.id)

        status_label = STATUS_LABELS.get(order.status, order.status)
        created_by = current_user.email if current_user.is_authenticated else ""
        created_at = order.created_at.strftime("%Y-%m-%d %H:%M") if order.created_at else ""

        msg = EmailMessage()
        msg["Subject"] = f"NeoFab: New order #{order.id}"
        msg["From"] = smtp_from
        msg["To"] = ", ".join(recipients)
        if order.user and order.user.email:
            msg["Reply-To"] = order.user.email

        body_lines = [
            "A new order has been created.",
            f"ID: {order.id}",
            f"Title: {order.title}",
            f"Status: {status_label}",
            f"Created by: {created_by}",
            f"Created at: {created_at}",
            f"Link: {order_url}",
        ]
        if order.summary_short:
            body_lines.extend(["", "Summary:", order.summary_short])

        msg.set_content("\n".join(body_lines))

        if smtp_use_ssl:
            server = smtplib.SMTP_SSL(smtp_host, smtp_port, timeout=10)
        else:
            server = smtplib.SMTP(smtp_host, smtp_port, timeout=10)

        with server:
            server.ehlo()
            if smtp_use_tls and not smtp_use_ssl:
                server.starttls()
                server.ehlo()
            if smtp_user:
                server.login(smtp_user, smtp_password or "")
            server.send_message(msg, from_addr=smtp_user or smtp_from)

        app.logger.info(
            "Sent admin notification for order %s to %s",
            order.id,
            ", ".join(recipients),
        )
        return True
    except Exception:
        app.logger.exception(
            "Failed to send admin notification for order %s", getattr(order, "id", "?")
        )
        return False


def send_order_status_change_notification(order: Order, old_status: str, new_status: str) -> bool:
    """
    Notify admins and the order owner about a status change.
    Never raises; returns True on success, False otherwise.
    """
    try:
        settings = load_app_settings(app, force_reload=True)
        smtp_host = settings.get("smtp_host")
        smtp_port = settings.get("smtp_port")
        smtp_use_tls = bool(settings.get("smtp_use_tls"))
        smtp_use_ssl = bool(settings.get("smtp_use_ssl"))
        smtp_user = settings.get("smtp_user")
        smtp_password = settings.get("smtp_password")
        smtp_from = settings.get("smtp_from_address")

        if not smtp_host or not smtp_port or not smtp_from:
            app.logger.info("SMTP not configured, skipping status notification.")
            return False

        recipients = _collect_order_recipients(order, include_owner=True)
        if not recipients:
            app.logger.info("No recipients found, skipping status notification.")
            return False

        try:
            order_url = url_for("order_detail", order_id=order.id, _external=True)
        except Exception:
            order_url = url_for("order_detail", order_id=order.id)

        old_label = STATUS_LABELS.get(old_status, old_status)
        new_label = STATUS_LABELS.get(new_status, new_status)
        changed_by = current_user.email if current_user.is_authenticated else ""

        msg = EmailMessage()
        msg["Subject"] = f"NeoFab: Order #{order.id} status changed to {new_label}"
        msg["From"] = smtp_from
        msg["To"] = ", ".join(recipients)
        if order.user and order.user.email:
            msg["Reply-To"] = order.user.email

        body_lines = [
            "The order status has changed.",
            f"ID: {order.id}",
            f"Title: {order.title}",
            f"Status: {old_label} -> {new_label}",
            f"Changed by: {changed_by}",
            f"Link: {order_url}",
        ]
        if order.summary_short:
            body_lines.extend(["", "Summary:", order.summary_short])

        msg.set_content("\n".join(body_lines))

        if smtp_use_ssl:
            server = smtplib.SMTP_SSL(smtp_host, smtp_port, timeout=10)
        else:
            server = smtplib.SMTP(smtp_host, smtp_port, timeout=10)

        with server:
            server.ehlo()
            if smtp_use_tls and not smtp_use_ssl:
                server.starttls()
                server.ehlo()
            if smtp_user:
                server.login(smtp_user, smtp_password or "")
            server.send_message(msg, from_addr=smtp_user or smtp_from)

        app.logger.info(
            "Sent status change notification for order %s to %s",
            order.id,
            ", ".join(recipients),
        )
        return True
    except Exception:
        app.logger.exception(
            "Failed to send status change notification for order %s", getattr(order, "id", "?")
        )
        return False


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


@app.route("/login", methods=["GET", "POST"])
def login():
    """Login-Formular & Login-Logik."""
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        trans = inject_globals().get("t")
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        user = User.query.filter_by(email=email).first()
        if user and user.check_password(password):
            login_user(user)
            load_app_settings(app)
            session.permanent = True
            session[SESSION_LAST_ACTIVE_KEY] = datetime.utcnow().isoformat()
            user.last_login_at = datetime.utcnow()
            db.session.commit()

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

    if request.method == "POST":
        trans = inject_globals().get("t")
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        password2 = request.form.get("password2", "")

        # einfache Validierung
        if not email or not password:
            flash(trans("flash_required_fields"), "danger")
        elif password != password2:
            flash(trans("flash_passwords_mismatch"), "danger")
        elif User.query.filter_by(email=email).first():
            flash(trans("flash_email_registered"), "warning")
        else:
            user = User(
                email=email,
                role="user",
                salutation=request.form.get("salutation") or None,
                first_name=request.form.get("first_name") or None,
                last_name=request.form.get("last_name") or None,
                address=request.form.get("address") or None,
                position=request.form.get("position") or None,
                cost_center=request.form.get("cost_center") or None,
                study_program=request.form.get("study_program") or None,
                note=request.form.get("note") or None,
            )
            user.set_password(password)
            db.session.add(user)
            db.session.commit()
            flash(trans("flash_registration_success"), "success")
            return redirect(url_for("login"))

    return render_template("register.html")


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

    if request.method == "POST":
        trans = inject_globals().get("t")
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

                if new_password:
                    user.set_password(new_password)

                db.session.commit()
                flash(trans("flash_profile_updated"), "success")
                return redirect(url_for("profile"))

    return render_template("profile.html", user=user)


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
    videos = TrainingVideo.query.order_by(TrainingVideo.sort_order.asc(), TrainingVideo.created_at.desc()).all()

    def build_video_entry(video: TrainingVideo) -> dict:
        vid = extract_youtube_id(video.youtube_url)
        embed_url = (
            f"https://www.youtube-nocookie.com/embed/{vid}"
            if vid
            else video.youtube_url
        )
        thumb_url = f"https://img.youtube.com/vi/{vid}/hqdefault.jpg" if vid else None
        return {
            "video": video,
            "embed_url": embed_url,
            "thumb_url": thumb_url,
        }

    video_entries = [build_video_entry(v) for v in videos]
    return render_template("tutorials.html", videos=video_entries)


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
    materials = Material.query.order_by(Material.name.asc()).all()
    colors = Color.query.order_by(Color.name.asc()).all()
    cost_centers = CostCenter.query.order_by(CostCenter.name.asc()).all()

    if request.method == "POST":
        title = request.form.get("title", "").strip()
        description = request.form.get("description", "").strip()

        # --- Status-Handling ---
        if current_user.role == "admin":
            # Admin darf initialen Status w├ñhlen
            status = request.form.get("status", "new")
            valid_status_values = [s[0] for s in ORDER_STATUSES]
            if status not in valid_status_values:
                status = "new"
        else:
            # Normale Nutzer starten immer mit "new"
            status = "new"
        # ------------------------

        # Material / Farbe / Kostenstelle (optional)
        material_id = request.form.get("material_id") or None
        color_id = request.form.get("color_id") or None
        cost_center_id = request.form.get("cost_center_id") or None

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
        project_purpose = request.form.get("project_purpose", "").strip() or None
        project_use_case = request.form.get("project_use_case", "").strip() or None
        learning_points = request.form.get("learning_points", "").strip() or None
        background_info = request.form.get("background_info", "").strip() or None
        project_url = request.form.get("project_url", "").strip() or None
        tags_value = request.form.get("tags", "").strip() or None
        language = request.form.get("language", "").strip().lower() or "en"
        if language not in SUPPORTED_LANGS:
            language = "en"

        trans = inject_globals().get("t")

        if not title:
            flash(trans("flash_title_required"), "danger")
            return render_template(
                "orders_new.html",
                order_statuses=ORDER_STATUSES,
                materials=materials,
                colors=colors,
                cost_centers=cost_centers,
            )

        order = Order(
            title=title,
            description=description or None,
            status=status,
            user_id=current_user.id,
            public_allow_poster=public_allow_poster,
            public_allow_web=public_allow_web,
            public_allow_social=public_allow_social,
            public_display_name=public_display_name,
            summary_short=summary_short,
            summary_long=summary_long,
            project_purpose=project_purpose,
            project_use_case=project_use_case,
            learning_points=learning_points,
            background_info=background_info,
            project_url=project_url,
        )

        # Nur sinnvolle IDs setzen
        if material_id:
            try:
                order.material_id = int(material_id)
            except ValueError:
                pass

        if color_id:
            try:
                order.color_id = int(color_id)
            except ValueError:
                pass
        if cost_center_id:
            try:
                order.cost_center_id = int(cost_center_id)
            except ValueError:
                pass

        db.session.add(order)
        db.session.commit()

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

                db.session.commit()

                app.logger.debug(
                    f"[new_order] Uploaded file for order {order.id}: "
                    f"OrderFile.id={order_file.id}, stored_name={stored_name!r}"
                )
        # ===================================================================

        app.logger.debug(
            f"[new_order] Created order id={order.id}, title={order.title!r}, "
            f"status={order.status!r}, user={current_user.email}, "
            f"material_id={order.material_id}, color_id={order.color_id}"
        )

        send_admin_order_notification(order)

        flash(trans("flash_order_created"), "success")
        return redirect(url_for("dashboard"))

    # GET
    return render_template(
        "orders_new.html",
        order_statuses=ORDER_STATUSES,
        materials=materials,
        colors=colors,
        cost_centers=cost_centers,
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
    if current_user.role != "admin" and order.user_id != current_user.id:
        abort(403)

    if request.method == "POST":
        app.logger.debug(f"[order_detail] POST data for order {order.id}: {dict(request.form)}")
        trans = inject_globals().get("t")

        action = request.form.get("action")

        # --- 1) Auftragsdaten aktualisieren --------------------------------
        if action == "update_order":
            title = request.form.get("title", "").strip()
            description = request.form.get("description", "").strip()
            status = request.form.get("status", order.status)
            previous_status = order.status

            public_allow_poster = bool(request.form.get("public_allow_poster"))
            public_allow_web = bool(request.form.get("public_allow_web"))
            public_allow_social = bool(request.form.get("public_allow_social"))
            public_display_name = request.form.get("public_display_name", "").strip() or None

            summary_short = request.form.get("summary_short", "").strip() or None
            summary_long = request.form.get("summary_long", "").strip() or None
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
                order.title = title
                order.description = description or None

                # Material / Farbe / Kostenstelle aktualisieren (f├╝r alle Rollen erlaubt)
                material_id = request.form.get("material_id") or None
                color_id = request.form.get("color_id") or None
                cost_center_id = request.form.get("cost_center_id") or None

                if material_id:
                    try:
                        order.material_id = int(material_id)
                    except ValueError:
                        order.material_id = None
                else:
                    order.material_id = None

                if color_id:
                    try:
                        order.color_id = int(color_id)
                    except ValueError:
                        order.color_id = None
                else:
                    order.color_id = None

                if cost_center_id:
                    try:
                        order.cost_center_id = int(cost_center_id)
                    except ValueError:
                        order.cost_center_id = None
                else:
                    order.cost_center_id = None

                # ├ûffentlichkeits-Felder ├╝bernehmen
                order.public_allow_poster = public_allow_poster
                order.public_allow_web = public_allow_web
                order.public_allow_social = public_allow_social
                order.public_display_name = public_display_name
                order.summary_short = summary_short
                order.summary_long = summary_long
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
                    valid_status_values = [s[0] for s in ORDER_STATUSES]
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
                    send_order_status_change_notification(order, previous_status, order.status)

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
                    send_order_status_change_notification(order, previous_status, order.status)
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
            file_quantity_raw = request.form.get("file_quantity", "").strip()
            try:
                file_quantity = max(1, int(file_quantity_raw or "1"))
            except ValueError:
                file_quantity = 1

            if not file or not file.filename:
                flash(trans("flash_select_file"), "warning")
                return redirect(url_for("order_detail", order_id=order.id))

            original_name = file.filename
            safe_name = secure_filename(original_name)

            _, ext = os.path.splitext(safe_name)
            ext = ext.lower().lstrip(".")  # "stl" oder "3mf"

            allowed_ext = {"stl", "3mf"}
            if ext not in allowed_ext:
                flash(trans("flash_invalid_file"), "warning")
                return redirect(url_for("order_detail", order_id=order.id))

            # OrderFile-Eintrag mit Platzhalter
            order_file = OrderFile(
                order_id=order.id,
                original_name=original_name,
                stored_name="",
                file_type=ext,
                note=file_note,
                quantity=file_quantity,
            )
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

            db.session.commit()

            app.logger.debug(
                f"[order_detail] Uploaded extra file for order {order.id}: "
                f"OrderFile.id={order_file.id}, stored_name={stored_name!r}"
            )

            flash(trans("flash_file_uploaded"), "success")
            return redirect(url_for("order_detail", order_id=order.id))

        # --- 5) Projektbild hochladen --------------------------------------
        elif action == "upload_image":
            file = request.files.get("image_file")
            image_note = (request.form.get("image_note") or "").strip()
            if image_note:
                image_note = image_note[:255]
            if not file or not file.filename:
                flash(trans("flash_select_image"), "warning")
                return redirect(url_for("order_detail", order_id=order.id))

            original_name = file.filename
            safe_name = secure_filename(original_name)

            _, ext = os.path.splitext(safe_name)
            ext = ext.lower().lstrip(".")

            allowed_ext = {"png", "jpg", "jpeg", "gif", "webp"}
            if ext not in allowed_ext:
                flash(trans("flash_invalid_image"), "warning")
                return redirect(url_for("order_detail", order_id=order.id))

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

            flash(trans("flash_image_uploaded"), "success")
            return redirect(url_for("order_detail", order_id=order.id))

        # --- 6) Datei l├Âschen ----------------------------------------------
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

    # --- Lese-Status aktualisieren (GET + nach POST-Redirect) --------------
    now = datetime.utcnow()
    read_status = OrderReadStatus.query.filter_by(
        order_id=order.id,
        user_id=current_user.id,
    ).first()

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
    cost_centers = CostCenter.query.order_by(CostCenter.name.asc()).all()

    app.logger.debug(
        f"[order_detail] Render detail for order {order.id}: status={order.status!r}, "
        f"messages_count={len(messages)}, material_id={order.material_id}, color_id={order.color_id}"
    )
    return render_template(
        "order_detail.html",
        order=order,
        messages=messages,
        order_statuses=ORDER_STATUSES,
        materials=materials,
        colors=colors,
        cost_centers=cost_centers,
        tags_value=order.tags_entry.tags if order.tags_entry else "",
    )


@app.route("/orders/<int:order_id>/messages-fragment")
@login_required
def order_messages_fragment(order_id):
    """
    Liefert nur den Nachrichten-Thread als HTML-Fragment fÃ¼r Auto-Refresh.
    """
    order = Order.query.get_or_404(order_id)

    # Access control wie in order_detail
    if current_user.role != "admin" and order.user_id != current_user.id:
        abort(403)

    messages = order.messages
    return render_template("order_messages_fragment.html", messages=messages)


@app.route("/orders/<int:order_id>/images/<int:image_id>/thumbnail")
@login_required
def order_image_thumbnail(order_id, image_id):
    order = Order.query.get_or_404(order_id)
    if current_user.role != "admin" and order.user_id != current_user.id:
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


@app.route("/orders/<int:order_id>/images/<int:image_id>/download")
@login_required
def download_order_image(order_id, image_id):
    trans = inject_globals().get("t")
    order = Order.query.get_or_404(order_id)
    if current_user.role != "admin" and order.user_id != current_user.id:
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
    if current_user.role != "admin" and order.user_id != current_user.id:
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


# ============================================================
# Dashboard
# ============================================================

@app.route("/dashboard")
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

    # 1) Orders laden (je nach Rolle)
    if current_user.role == "admin":
        orders = (
            Order.query
            .order_by(Order.created_at.desc())
            .all()
        )
    else:
        orders = (
            Order.query
            .filter_by(user_id=current_user.id)
            .order_by(Order.created_at.desc())
            .all()
        )

    app.logger.debug(f"[dashboard] Loaded {len(orders)} orders")

    if not orders:
        return render_template(
            "dashboard.html",
            orders=[],
            last_new_message={},
            status_labels=STATUS_LABELS,
            file_counts={},   # wichtig, damit Template file_counts kennt
        )

    order_ids = [o.id for o in orders]
    for o in orders:
        app.logger.debug(
            f"[dashboard] Order id={o.id}, title={o.title!r}, status={o.status!r}"
        )

    # 2) Anzahl Dateien pro Order ermitteln
    file_counts = {}
    if order_ids:
        file_count_rows = (
            db.session.query(
                OrderFile.order_id,
                func.count(OrderFile.id)
            )
            .filter(OrderFile.order_id.in_(order_ids))
            .group_by(OrderFile.order_id)
            .all()
        )
        file_counts = {order_id: count for order_id, count in file_count_rows}

    app.logger.debug(f"[dashboard] file_counts: {file_counts}")

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

    # 4) Read-Zeitpunkte aus der Session holen (pro Order)
    read_by_order = {}
    for oid in order_ids:
        session_key = f"order_last_read_{oid}"
        iso_val = session.get(session_key)
        if iso_val:
            try:
                read_by_order[oid] = datetime.fromisoformat(iso_val)
            except Exception:
                read_by_order[oid] = None

    app.logger.debug(f"[dashboard] read_by_order (session): {read_by_order}")

    # 5) "last_new_message" pro Order berechnen (f├╝r "new message"-Badge)
    last_new_message = {}
    for o in orders:
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

    return render_template(
        "dashboard.html",
        orders=orders,
        last_new_message=last_new_message,
        status_labels=STATUS_LABELS,
        file_counts=file_counts,
    )



# ============================================================
# Logout
# ============================================================

@app.route("/logout")
@login_required
def logout():
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
        return dt.strftime("%Y-%m-%d %H:%M") if dt else ""

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

    generated_at = fmt_dt(datetime.now())

    return {
        "app_name": "NeoFab",
        "app_version": APP_VERSION,
        "pdf_generated_at": generated_at,
        "order": order,
        "order_dict": {
            "id": order.id,
            "title": order.title,
            "status": STATUS_LABELS.get(order.status, order.status),
            "owner": order.user.email if order.user else "",
            "salutation": order.user.salutation if order.user else "",
            "first_name": order.user.first_name if order.user else "",
            "last_name": order.user.last_name if order.user else "",
            "address": order.user.address if order.user else "",
            "position": order.user.position if order.user else "",
            "study_program": order.user.study_program if order.user else "",
            "material": order.material.name if order.material else "",
            "color": order.color.name if order.color else "",
            "cost_center": order.cost_center.name if order.cost_center else "",
            "created_at": fmt_dt(order.created_at),
            "updated_at": fmt_dt(order.updated_at),
            "description": order.description or "",
            "summary_short": order.summary_short or "",
            "summary_long": order.summary_long or "",
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


def _build_order_pdf(order, translator) -> bytes:
    """
    Baut ein minimalistisches PDF (A4) mit Auftragsdetails.
    """
    lines: List[Tuple[str, str]] = []
    add = lambda label, value: lines.append((label, value)) if value else None

    add("NeoFab", f"Version {APP_VERSION}")
    add("", "")
    add("Order ID", f"#{order.id}")
    add(translator("order_title_label"), order.title)
    add(translator("order_status_label"), STATUS_LABELS.get(order.status, order.status))
    add(translator("order_owner_label"), order.user.email if order.user else "")
    add(translator("order_material_label"), order.material.name if order.material else "")
    add(translator("order_color_label"), order.color.name if order.color else "")
    add(translator("order_cost_center_label"), order.cost_center.name if order.cost_center else "")
    add(translator("order_created_label"), order.created_at.strftime("%Y-%m-%d %H:%M") if order.created_at else "")
    add(translator("order_updated_label"), order.updated_at.strftime("%Y-%m-%d %H:%M") if order.updated_at else "")
    add(translator("order_summary_short"), order.summary_short or "")
    add(translator("order_summary_long"), order.summary_long or "")
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
            meta.append(msg.created_at.strftime("%Y-%m-%d %H:%M"))
        if msg.user:
            meta.append(msg.user.email)
        meta_str = " - ".join(meta)
        content = msg.content.replace("\r", " ").replace("\n", " ").strip()
        add(f"ÔÇó {meta_str}", content)

    add("", "")
    add(translator("files_header"), "")
    for f in order.files:
        parts = []
        if f.file_type:
            parts.append(f.file_type.upper())
        qty = f.quantity or 1
        parts.append(f"qty {qty}")
        if f.note:
            parts.append(f.note)
        add(f"ÔÇó {f.original_name}", " | ".join(parts))

    add("", "")
    add(translator("images_header"), "")
    for img in order.images:
        meta = []
        if img.filesize:
            meta.append(f"{(img.filesize / 1024):.1f} KB")
        if img.uploaded_at:
            meta.append(img.uploaded_at.strftime("%Y-%m-%d %H:%M"))
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
