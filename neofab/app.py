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
import binascii
import mimetypes
import os
import logging
import re
import math
import struct
from urllib.parse import parse_qs, urlparse

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
    DEFAULT_SETTINGS,
    SETTINGS_FILE,
    coerce_positive_int,
    load_app_settings,
    save_app_settings,
)
from i18n_utils import DEFAULT_LANG, SUPPORTED_LANGS, get_translations
from legal_markdown import render_legal_markdown
from notifications import (
    send_admin_order_notification,
    send_order_status_change_notification,
)
from schema_utils import ensure_training_playlist_schema
from status_messages import (
    ORDER_STATUS_DEFS,
    PRINT_JOB_STATUS_DEFS,
    build_status_context,
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
    OrderPrintJob,
    OrderImage,
    OrderTag,
    Material,
    Color,
    CostCenter,
    PrinterProfile,
    FilamentMaterial,
    TrainingPlaylist,
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

GCODE_UPLOAD_FOLDER = BASE_DIR / "uploads" / "gcode"
os.makedirs(GCODE_UPLOAD_FOLDER, exist_ok=True)
app.config["GCODE_UPLOAD_FOLDER"] = str(GCODE_UPLOAD_FOLDER)

TRAINING_UPLOAD_FOLDER = BASE_DIR / "uploads" / "tutorials"
os.makedirs(TRAINING_UPLOAD_FOLDER, exist_ok=True)
app.config["TRAINING_UPLOAD_FOLDER"] = str(TRAINING_UPLOAD_FOLDER)

# Max width for generated thumbnails (px)
THUMBNAIL_MAX_WIDTH = 200

# Thumbnail sizes for STL previews
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


# Maximal erlaubte Upload-Gr├Â├ƒe (z.B. 50 MB)
app.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024  # 50 MB

# Einfache Logging-Konfiguration
logging.basicConfig(level=logging.DEBUG)
app.logger.setLevel(logging.DEBUG)

# Auftrags-Status-Codes (interne Werte + Labels)
ORDER_STATUSES = [(item["key"], item["label"]) for item in ORDER_STATUS_DEFS]
ORDER_STATUS_VALUES = [item["key"] for item in ORDER_STATUS_DEFS]

# Mapping der Status-Codes zu lesbaren Labels

# Abw├ñrtskompatibilit├ñt f├╝r alte deutsche Statuswerte

PRINT_JOB_STATUSES = [(item["key"], item["label"]) for item in PRINT_JOB_STATUS_DEFS]
PRINT_JOB_STATUS_VALUES = [item["key"] for item in PRINT_JOB_STATUS_DEFS]

# Secret Key & Datenbank-Config
app.config["SECRET_KEY"] = os.environ.get("NEOFAB_SECRET_KEY", "dev-secret-change-me")

# SQLite-DB im Projektverzeichnis (absoluter Pfad)
db_path = BASE_DIR / "neofab.db"
app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{db_path}"

app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

load_app_settings(app)


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

    status_context = get_status_context(t)
    return {
        "app_version": APP_VERSION,
        "status_labels": status_context["order_status_labels"],
        "status_styles": status_context["order_status_styles"],
        "print_job_status_labels": status_context["print_job_status_labels"],
        "print_job_status_styles": status_context["print_job_status_styles"],
        "order_statuses": status_context["order_statuses"],
        "print_job_statuses": status_context["print_job_statuses"],
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
                        original_name VARCHAR(255) NOT NULL,
                        stored_name VARCHAR(255) NOT NULL,
                        note VARCHAR(255),
                        status VARCHAR(50) NOT NULL DEFAULT 'upload',
                        started_at DATETIME,
                        duration_min INTEGER,
                        filament_m FLOAT,
                        filament_g FLOAT,
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
        if "filesize" not in cols:
            statements.append("ALTER TABLE order_print_jobs ADD COLUMN filesize INTEGER")
        if "uploaded_at" not in cols:
            statements.append(
                "ALTER TABLE order_print_jobs ADD COLUMN uploaded_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP"
            )

        for stmt in statements:
            db.session.execute(text(stmt))
        if statements:
            db.session.commit()
    except Exception:
        app.logger.exception("Failed to ensure order_print_jobs table exists")


with app.app_context():
    ensure_order_file_columns()
    ensure_order_image_columns()
    ensure_training_videos_table()
    ensure_printer_profiles_table()
    ensure_filament_materials_table()
    ensure_order_estimation_columns()
    ensure_order_print_jobs_table()


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

    order_file.has_3d_preview = True

    if file_type != "stl":
        order_file.preview_status = "unsupported"
        return

    if not source_path.exists():
        order_file.preview_status = "missing"
        return

    thumb_sm_name, thumb_lg_name = _build_model_thumbnail_names(order_file.stored_name)
    thumb_folder = source_path.parent / "thumbnails"
    thumb_sm_path = thumb_folder / thumb_sm_name
    thumb_lg_path = thumb_folder / thumb_lg_name

    small_ok = thumb_sm_path.exists()
    large_ok = thumb_lg_path.exists()
    if not small_ok or not large_ok:
        gen_small, gen_large = generate_stl_thumbnails(source_path, thumb_sm_path, thumb_lg_path)
        small_ok = small_ok or gen_small
        large_ok = large_ok or gen_large

    order_file.thumb_sm_path = thumb_sm_name if small_ok else None
    order_file.thumb_lg_path = thumb_lg_name if large_ok else None
    order_file.preview_status = "ok" if (small_ok or large_ok) else "failed"



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
    materials = Material.query.order_by(Material.name.asc()).all()
    colors = Color.query.order_by(Color.name.asc()).all()
    cost_centers = CostCenter.query.order_by(CostCenter.name.asc()).all()
    printer_profiles = PrinterProfile.query.filter_by(active=True).order_by(PrinterProfile.name.asc()).all()
    filament_materials = FilamentMaterial.query.filter_by(active=True).order_by(FilamentMaterial.name.asc()).all()
    trans = inject_globals().get("t")
    status_context = get_status_context(trans)

    if request.method == "POST":
        title = request.form.get("title", "").strip()
        description = request.form.get("description", "").strip()

        # --- Status-Handling ---
        if current_user.role == "admin":
            # Admin darf initialen Status w├ñhlen
            status = request.form.get("status", "new")
            valid_status_values = ORDER_STATUS_VALUES
            if status not in valid_status_values:
                status = "new"
        else:
            # Normale Nutzer starten immer mit "new"
            status = "new"
        # ------------------------

        # Material / Farbe / Kostenstelle / Druckerprofil / Filament (optional)
        material_id = request.form.get("material_id") or None
        color_id = request.form.get("color_id") or None
        cost_center_id = request.form.get("cost_center_id") or None
        printer_profile_id = request.form.get("printer_profile_id") or None
        filament_material_id = request.form.get("filament_material_id") or None

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

        if not title:
            flash(trans("flash_title_required"), "danger")
            return render_template(
                "orders_new.html",
                order_statuses=status_context["order_statuses"],
                materials=materials,
                colors=colors,
                cost_centers=cost_centers,
                printer_profiles=printer_profiles,
                filament_materials=filament_materials,
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

        def _select_active_id(model, raw_id):
            if not raw_id:
                return None
            try:
                raw_int = int(raw_id)
            except ValueError:
                return None
            entry = model.query.filter_by(id=raw_int, active=True).first()
            return entry.id if entry else None

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
        order.printer_profile_id = _select_active_id(PrinterProfile, printer_profile_id)
        order.filament_material_id = _select_active_id(FilamentMaterial, filament_material_id)

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
                update_order_file_preview(order_file, full_path)

                db.session.commit()

                app.logger.debug(
                    f"[new_order] Uploaded file for order {order.id}: "
                    f"OrderFile.id={order_file.id}, stored_name={stored_name!r}"
                )
        # ===================================================================

        app.logger.debug(
            f"[new_order] Created order id={order.id}, title={order.title!r}, "
            f"status={order.status!r}, user={current_user.email}, "
            f"material_id={order.material_id}, color_id={order.color_id}, "
            f"printer_profile_id={order.printer_profile_id}, filament_material_id={order.filament_material_id}"
        )

        send_admin_order_notification(app, order, status_context["order_status_labels"])
        flash(trans("flash_order_created"), "success")
        return redirect(url_for("dashboard"))

    # GET
    return render_template(
        "orders_new.html",
        order_statuses=status_context["order_statuses"],
        materials=materials,
        colors=colors,
        cost_centers=cost_centers,
        printer_profiles=printer_profiles,
        filament_materials=filament_materials,
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
                current_printer_profile_id = order.printer_profile_id
                current_filament_material_id = order.filament_material_id

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
                    send_order_status_change_notification(
                        app,
                        order,
                        previous_status,
                        order.status,
                        status_labels,
                    )
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
            update_order_file_preview(order_file, full_path)

            db.session.commit()

            app.logger.debug(
                f"[order_detail] Uploaded extra file for order {order.id}: "
                f"OrderFile.id={order_file.id}, stored_name={stored_name!r}"
            )

            flash(trans("flash_file_uploaded"), "success")
            return redirect(url_for("order_detail", order_id=order.id))

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
            file_quantity_raw = request.form.get("file_quantity", "").strip()
            try:
                file_quantity = max(1, int(file_quantity_raw or "1"))
            except ValueError:
                file_quantity = 1

            order_file.note = file_note
            order_file.quantity = file_quantity
            db.session.commit()

            flash(trans("flash_file_updated"), "success")
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

        # --- 6) G-Code hochladen (nur Admin) -------------------------------
        elif action == "upload_print_job":
            if current_user.role != "admin":
                abort(403)

            file = request.files.get("gcode_file")
            note = (request.form.get("gcode_note") or "").strip()
            if note:
                note = note[:255]

            started_at_raw = (request.form.get("print_started_at") or "").strip()
            duration_raw = (request.form.get("print_duration_min") or "").strip()
            filament_m_raw = (request.form.get("print_filament_m") or "").strip()
            filament_g_raw = (request.form.get("print_filament_g") or "").strip()
            status_raw = (request.form.get("print_status") or "").strip() or "upload"

            if not file or not file.filename:
                flash(trans("flash_print_job_select_file"), "warning")
                return redirect(url_for("order_detail", order_id=order.id))

            original_name = file.filename
            safe_name = secure_filename(original_name)

            _, ext = os.path.splitext(safe_name)
            ext = ext.lower().lstrip(".")
            allowed_ext = {"gcode", "gco", "gc"}
            if ext not in allowed_ext:
                flash(trans("flash_print_job_invalid_file"), "warning")
                return redirect(url_for("order_detail", order_id=order.id))

            started_at = None
            if started_at_raw:
                try:
                    started_at = datetime.fromisoformat(started_at_raw)
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

            valid_statuses = set(PRINT_JOB_STATUS_VALUES)
            status = status_raw if status_raw in valid_statuses else "upload"

            printer_profile_id = request.form.get("printer_profile_id") or None
            filament_material_id = request.form.get("filament_material_id") or None
            current_printer_profile_id = order.printer_profile_id
            current_filament_material_id = order.filament_material_id

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

            order.printer_profile_id = _select_profile_id(
                PrinterProfile,
                printer_profile_id,
                current_printer_profile_id,
            )
            order.filament_material_id = _select_profile_id(
                FilamentMaterial,
                filament_material_id,
                current_filament_material_id,
            )

            job = OrderPrintJob(
                order_id=order.id,
                original_name=original_name,
                stored_name="",
                note=note or None,
                status=status,
                started_at=started_at,
                duration_min=duration_min,
                filament_m=filament_m,
                filament_g=filament_g,
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

            db.session.commit()
            flash(trans("flash_print_job_uploaded"), "success")
            return redirect(url_for("order_detail", order_id=order.id))

        # --- 7) G-Code l├Âschen (nur Admin) ---------------------------------
        elif action == "update_print_job":
            if current_user.role != "admin":
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
            status_raw = (request.form.get("edit_print_status") or "").strip()

            started_at = None
            if started_at_raw:
                try:
                    started_at = datetime.fromisoformat(started_at_raw)
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

            valid_statuses = set(PRINT_JOB_STATUS_VALUES)
            status = status_raw if status_raw in valid_statuses else (job.status or "upload")

            job.note = note or None
            job.status = status
            job.started_at = started_at
            job.duration_min = duration_min
            job.filament_m = filament_m
            job.filament_g = filament_g

            db.session.commit()
            flash(trans("flash_print_job_updated"), "success")
            return redirect(url_for("order_detail", order_id=order.id))

        elif action == "delete_print_job":
            if current_user.role != "admin":
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
            db.session.commit()
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

    print_jobs = (
        OrderPrintJob.query
        .filter_by(order_id=order.id)
        .order_by(OrderPrintJob.uploaded_at.desc())
        .all()
    )

    status_context = get_status_context(inject_globals().get("t"))
    app.logger.debug(
        f"[order_detail] Render detail for order {order.id}: status={order.status!r}, "
        f"messages_count={len(messages)}, material_id={order.material_id}, color_id={order.color_id}"
    )
    return render_template(
        "order_detail.html",
        order=order,
        messages=messages,
        order_statuses=status_context["order_statuses"],
        materials=materials,
        colors=colors,
        cost_centers=cost_centers,
        printer_profiles=printer_profiles,
        filament_materials=filament_materials,
        print_jobs=print_jobs,
        print_job_statuses=status_context["print_job_statuses"],
        print_job_status_labels=status_context["print_job_status_labels"],
        print_job_status_styles=status_context["print_job_status_styles"],
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


@app.route("/orders/<int:order_id>/files/<int:file_id>/thumbnail/<size>", methods=["GET", "POST"])
@login_required
def order_file_thumbnail(order_id, file_id, size):
    order = Order.query.get_or_404(order_id)
    if current_user.role != "admin" and order.user_id != current_user.id:
        abort(403)

    order_file = OrderFile.query.filter_by(id=file_id, order_id=order.id).first_or_404()
    if (order_file.file_type or "").lower() != "stl":
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
    if current_user.role != "admin" and order.user_id != current_user.id:
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


@app.route("/orders/<int:order_id>/print-jobs/<int:job_id>/download")
@login_required
def download_print_job(order_id, job_id):
    trans = inject_globals().get("t")
    order = Order.query.get_or_404(order_id)

    if current_user.role != "admin" and order.user_id != current_user.id:
        abort(403)

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


@app.route("/files/<int:file_id>/set-color", methods=["POST"])
@login_required
def set_file_color(file_id):
    order_file = OrderFile.query.get_or_404(file_id)
    order = Order.query.get_or_404(order_file.order_id)

    if current_user.role != "admin" and order.user_id != current_user.id:
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
    status_context = get_status_context(inject_globals().get("t"))

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
            status_labels=status_context["order_status_labels"],
            status_styles=status_context["order_status_styles"],
            file_counts={},   # wichtig, damit Template file_counts kennt
            print_job_counts={},
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

    print_job_counts = {}
    if order_ids:
        print_job_rows = (
            db.session.query(
                OrderPrintJob.order_id,
                func.count(OrderPrintJob.id),
            )
            .filter(OrderPrintJob.order_id.in_(order_ids))
            .group_by(OrderPrintJob.order_id)
            .all()
        )
        print_job_counts = {order_id: count for order_id, count in print_job_rows}

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
        status_labels=status_context["order_status_labels"],
        status_styles=status_context["order_status_styles"],
        file_counts=file_counts,
        print_job_counts=print_job_counts,
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

    generated_at = fmt_dt(datetime.now())
    status_context = get_status_context(translator)
    status_labels = status_context.get("order_status_labels", {})
    print_job_status_labels = status_context.get("print_job_status_labels", {})

    print_jobs = (
        OrderPrintJob.query
        .filter_by(order_id=order.id)
        .order_by(OrderPrintJob.uploaded_at.desc())
        .all()
    )

    return {
        "app_name": "NeoFab",
        "app_version": APP_VERSION,
        "pdf_generated_at": generated_at,
        "order": order,
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
                "note": job.note or "",
            }
            for job in print_jobs
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
    status_labels = get_status_context(translator).get("order_status_labels", {})

    add("NeoFab", f"Version {APP_VERSION}")
    add("", "")
    add("Order ID", f"#{order.id}")
    add(translator("order_title_label"), order.title)
    add(translator("order_status_label"), status_labels.get(order.status, order.status))
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
        if job.started_at:
            parts.append(
                f"{translator('print_jobs_table_started_at')} {job.started_at.strftime('%Y-%m-%d %H:%M')}"
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
            meta.append(job.uploaded_at.strftime("%Y-%m-%d %H:%M"))
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
