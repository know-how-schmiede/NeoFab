from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
import os
import secrets
import json
import shutil
from typing import Callable, Optional
from urllib.parse import parse_qs, urlparse
import smtplib
from email.message import EmailMessage
from zoneinfo import ZoneInfo

from flask import (
    Blueprint,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from flask_login import current_user
from sqlalchemy import func
from sqlalchemy.exc import OperationalError
from werkzeug.utils import secure_filename

from auth_utils import roles_required
from audit_logs import DELETE_LOG_FILE, delete_log_file, list_log_files, read_log_entries, write_audit_log
from config import (
    DASHBOARD_ROWS_PER_PAGE_OPTIONS,
    EMAIL_ACTION_DEFS,
    EMAIL_ACTION_KEYS,
    EMAIL_ACTION_STATE_DISABLED,
    EMAIL_ACTION_STATE_ENABLED,
    SETTINGS_FILE,
    coerce_dashboard_rows_per_page,
    coerce_bool,
    coerce_time_display_offset_hours,
    coerce_positive_int,
    load_app_settings,
    normalize_registration_domains,
    serialize_registration_domains,
    normalize_email_actions,
    save_app_settings,
)
from schema_utils import ensure_training_playlist_schema
from status_messages import (
    STATUS_GROUP_DEFS,
    STATUS_STYLE_OPTIONS,
    build_status_context,
    default_label,
    filter_status_messages,
    resolve_status_messages,
)
from models import (
    Color,
    CostCenter,
    Material,
    TrainingPlaylist,
    TrainingVideo,
    User,
    Announcement,
    AnnouncementRead,
    PrinterProfile,
    FilamentMaterial,
    Order,
    OrderArea,
    OrderFile,
    OrderImage,
    OrderMessage,
    OrderPosterFile,
    OrderProcurementArticle,
    OrderPrintJob,
    OrderReadStatus,
    OrderTag,
    OrderCategory,
    UserOrderCategoryPermission,
    UserOrderAreaPreference,
    db,
)
from notifications import send_user_welcome_notification
from version import APP_VERSION

USER_ROLE_OPTIONS = [
    ("user", "role_user"),
    ("admin", "role_admin"),
    ("worker", "role_worker"),
]
USER_ROLE_VALUES = {value for value, _label_key in USER_ROLE_OPTIONS}
USER_LANGUAGE_OPTIONS = [
    ("de", "Deutsch"),
    ("en", "English"),
    ("fr", "Francais"),
]
USER_LANGUAGE_VALUES = {value for value, _label in USER_LANGUAGE_OPTIONS}


def _translator(get_translator: Callable[[], Optional[Callable[[str], str]]]) -> Callable[[str], str]:
    trans = get_translator()
    return trans or (lambda key: key)


def _parse_nonnegative_float(value, default=None):
    if value in (None, ""):
        return default
    try:
        parsed = float(str(value).replace(",", "."))
    except (TypeError, ValueError):
        return None
    return parsed if parsed >= 0 else None


def _parse_bool(value, default=True):
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    text_value = str(value).strip().lower()
    if text_value in {"1", "true", "yes", "on", "ja"}:
        return True
    if text_value in {"0", "false", "no", "off", "nein"}:
        return False
    return default


def _pdf_escape(text_value: str) -> str:
    text_value = (text_value or "").replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    return text_value.encode("latin-1", "replace").decode("latin-1")


def _wrap_pdf_line(line: str, max_chars: int = 112) -> list[str]:
    text = str(line or "")
    if len(text) <= max_chars:
        return [text]
    words = text.split()
    rows: list[str] = []
    current = ""
    for word in words:
        if len(word) > max_chars:
            if current:
                rows.append(current)
                current = ""
            rows.extend(word[i : i + max_chars] for i in range(0, len(word), max_chars))
        elif not current:
            current = word
        elif len(current) + 1 + len(word) <= max_chars:
            current += " " + word
        else:
            rows.append(current)
            current = word
    if current:
        rows.append(current)
    return rows or [""]


def _truncate_pdf_cell(value, width: int, align: str = "left") -> str:
    text = str(value or "").replace("\r", " ").replace("\n", " ").strip()
    if len(text) > width:
        text = text[: max(width - 1, 0)] + "." if width > 1 else text[:width]
    if align == "right":
        return text.rjust(width)
    return text.ljust(width)


def _format_pdf_table_row(values: list[object], widths: list[int], right_aligned: set[int] | None = None) -> str:
    right_aligned = right_aligned or set()
    cells = [
        _truncate_pdf_cell(value, width, "right" if idx in right_aligned else "left")
        for idx, (value, width) in enumerate(zip(values, widths))
    ]
    return "  ".join(cells)


def _build_simple_text_pdf(lines: list[str]) -> bytes:
    rows: list[str] = []
    for line in lines:
        rows.extend(_wrap_pdf_line(line))

    lines_per_page = 56
    pages = [rows[i : i + lines_per_page] for i in range(0, len(rows), lines_per_page)] or [[]]
    renumbered = [
        "1 0 obj\n<< /Type /Catalog /Pages 3 0 R >>\nendobj\n",
        "2 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Courier >>\nendobj\n",
    ]
    page_numbers = []
    for page_index, page_rows in enumerate(pages):
        page_obj = 4 + page_index * 2
        content_obj = page_obj + 1
        page_numbers.append(page_obj)
        content_parts = ["BT", "/F1 8 Tf"]
        for idx, row in enumerate(page_rows):
            y = 805 - idx * 14
            content_parts.append(f"1 0 0 1 36 {y} Tm")
            content_parts.append(f"({_pdf_escape(row)}) Tj")
        content_parts.append("ET")
        content_stream = "\n".join(content_parts).encode("latin-1")
        renumbered.append(
            f"{page_obj} 0 obj\n"
            "<< /Type /Page /Parent 3 0 R /MediaBox [0 0 595 842] "
            f"/Contents {content_obj} 0 R /Resources << /Font << /F1 2 0 R >> >> >>\n"
            "endobj\n"
        )
        renumbered.append(
            f"{content_obj} 0 obj\n<< /Length {len(content_stream)} >>\nstream\n".encode("latin-1")
            + content_stream
            + b"\nendstream\nendobj\n"
        )
    kids = " ".join(f"{obj_no} 0 R" for obj_no in page_numbers)
    renumbered.insert(2, f"3 0 obj\n<< /Type /Pages /Count {len(pages)} /Kids [{kids}] >>\nendobj\n")

    pdf_parts: list[bytes] = [b"%PDF-1.4\n"]
    offsets = [0]
    current = len(pdf_parts[0])
    for obj in renumbered:
        chunk = obj if isinstance(obj, (bytes, bytearray)) else obj.encode("latin-1")
        offsets.append(current)
        pdf_parts.append(chunk)
        current += len(chunk)

    xref_start = current
    size = len(renumbered) + 1
    xref_lines = [b"xref\n", f"0 {size}\n".encode("latin-1"), b"0000000000 65535 f \n"]
    for off in offsets[1:]:
        xref_lines.append(f"{off:010d} 00000 n \n".encode("latin-1"))
    pdf_parts.extend(xref_lines)
    pdf_parts.append(
        b"trailer\n<< /Size "
        + str(size).encode("latin-1")
        + b" /Root 1 0 R >>\nstartxref\n"
        + str(xref_start).encode("latin-1")
        + b"\n%%EOF"
    )
    return b"".join(pdf_parts)


def create_admin_blueprint(get_translator: Callable[[], Optional[Callable[[str], str]]]) -> Blueprint:
    bp = Blueprint("admin", __name__, url_prefix="/admin")

    t = lambda key: _translator(get_translator)(key)

    def _fmt_datetime(value: datetime | None) -> str:
        if value is None:
            return ""

        try:
            app_timezone_name = os.environ.get("NEOFAB_TIMEZONE", "Europe/Berlin")
            try:
                app_local_tz = ZoneInfo(app_timezone_name)
            except Exception:
                app_local_tz = ZoneInfo("UTC")
            app_utc_tz = ZoneInfo("UTC")

            if value.tzinfo is None:
                value = value.replace(tzinfo=app_utc_tz)
            value = value.astimezone(app_local_tz)
        except Exception:
            pass

        try:
            settings = load_app_settings(current_app)
            offset_hours = int(settings.get("time_display_offset_hours", 0) or 0)
        except Exception:
            offset_hours = 0

        if offset_hours:
            value = value + timedelta(hours=offset_hours)

        try:
            return value.strftime("%Y-%m-%d %H:%M")
        except Exception:
            return ""

    admin_announcement_form_token_key = "admin_announcement_form_token"
    announcement_priority_meta = {
        "info": {"label": "announcement_priority_info", "icon": "bi-info-circle", "class": "text-primary"},
        "notice": {"label": "announcement_priority_notice", "icon": "bi-exclamation-circle", "class": "text-info"},
        "important": {"label": "announcement_priority_important", "icon": "bi-exclamation-triangle", "class": "text-warning"},
        "warning": {"label": "announcement_priority_warning", "icon": "bi-exclamation-octagon", "class": "text-danger"},
        "attention_email": {"label": "announcement_priority_attention_email", "icon": "bi-envelope-exclamation", "class": "text-danger fw-semibold"},
    }

    def new_admin_announcement_form_token() -> str:
        form_token = secrets.token_urlsafe(24)
        session[admin_announcement_form_token_key] = form_token
        return form_token

    def consume_admin_announcement_form_token() -> bool:
        form_token = (request.form.get("form_token") or "").strip()
        expected_token = session.pop(admin_announcement_form_token_key, None)
        return bool(form_token and expected_token and form_token == expected_token)

    def reject_duplicate_admin_announcement_submission():
        write_audit_log(
            current_app,
            "announcement_duplicate_ignored",
            details={"path": request.path},
            user=current_user,
        )
        flash(t("flash_duplicate_submission_ignored"), "warning")
        return redirect(url_for(".admin_announcement_list"))

    def normalize_training_video_order() -> None:
        """Ensure sequential sort_order without gaps."""
        ensure_training_playlist_schema()
        videos = TrainingVideo.query.order_by(
            TrainingVideo.sort_order.asc(), TrainingVideo.created_at.asc(), TrainingVideo.id.asc()
        ).all()
        dirty = False
        for idx, vid in enumerate(videos, start=1):
            if vid.sort_order != idx:
                vid.sort_order = idx
                dirty = True
        if dirty:
            db.session.commit()

    def swap_training_video(video_id: int, direction: str) -> None:
        """Swap the sort order of a video with its neighbor (up/down)."""
        normalize_training_video_order()
        videos = TrainingVideo.query.order_by(TrainingVideo.sort_order.asc(), TrainingVideo.id.asc()).all()
        idx = next((i for i, v in enumerate(videos) if v.id == video_id), None)
        if idx is None:
            return

        if direction == "up" and idx > 0:
            neighbor_idx = idx - 1
        elif direction == "down" and idx < len(videos) - 1:
            neighbor_idx = idx + 1
        else:
            return

        current = videos[idx]
        neighbor = videos[neighbor_idx]
        current.sort_order, neighbor.sort_order = neighbor.sort_order, current.sort_order
        db.session.commit()

    def _training_pdf_folder() -> Path:
        return Path(current_app.config["TRAINING_UPLOAD_FOLDER"])

    def _delete_training_pdf(video: TrainingVideo) -> None:
        if not video.pdf_filename:
            return
        try:
            pdf_path = _training_pdf_folder() / video.pdf_filename
            if pdf_path.exists():
                pdf_path.unlink()
        except OSError:
            current_app.logger.warning("Could not delete training PDF: %s", video.pdf_filename)

    def _save_training_pdf(video: TrainingVideo, file) -> tuple[bool, str | None]:
        if not file or not file.filename:
            return False, None
        safe_name = secure_filename(file.filename)
        if not safe_name.lower().endswith(".pdf"):
            return False, "invalid_pdf"

        folder = _training_pdf_folder()
        folder.mkdir(parents=True, exist_ok=True)
        stored_name = f"{video.id}_{safe_name}"
        full_path = folder / stored_name
        try:
            file.save(str(full_path))
        except Exception:
            return False, "save_failed"

        video.pdf_filename = stored_name
        video.pdf_original_name = file.filename
        try:
            video.pdf_filesize = full_path.stat().st_size
        except OSError:
            video.pdf_filesize = None
        return True, None

    def _delete_training_pdf_by_name(filename: str | None) -> None:
        if not filename:
            return
        try:
            pdf_path = _training_pdf_folder() / filename
            if pdf_path.exists():
                pdf_path.unlink()
        except OSError:
            current_app.logger.warning("Could not delete training PDF: %s", filename)

    def _count_folder_entries(folder: Path) -> tuple[int, int]:
        file_count = 0
        folder_count = 0
        if not folder.exists():
            return file_count, folder_count
        for child in folder.rglob("*"):
            if child.is_file():
                file_count += 1
            elif child.is_dir():
                folder_count += 1
        return file_count, folder_count

    def _remove_order_upload_folder(config_key: str, order_id: int) -> dict[str, object]:
        root = Path(current_app.config[config_key]).resolve()
        target = (root / f"order_{order_id}").resolve()
        details: dict[str, object] = {
            "order_id": order_id,
            "config_key": config_key,
            "path": str(target),
            "exists": target.exists(),
            "deleted": False,
        }
        try:
            if root not in target.parents or target.name != f"order_{order_id}":
                current_app.logger.warning("Refused to delete unsafe order folder: %s", target)
                details["error"] = "unsafe_path"
                write_audit_log(
                    current_app,
                    "order_delete_folder_refused",
                    user=current_user,
                    level="warning",
                    details=details,
                    log_file=DELETE_LOG_FILE,
                )
                return details
            if target.exists():
                file_count, folder_count = _count_folder_entries(target)
                details["file_count"] = file_count
                details["folder_count"] = folder_count
                shutil.rmtree(target)
                details["deleted"] = True
                write_audit_log(
                    current_app,
                    "order_delete_folder_deleted",
                    user=current_user,
                    details=details,
                    log_file=DELETE_LOG_FILE,
                )
            else:
                write_audit_log(
                    current_app,
                    "order_delete_folder_missing",
                    user=current_user,
                    details=details,
                    log_file=DELETE_LOG_FILE,
                )
        except Exception as exc:
            current_app.logger.warning("Could not delete order upload folder: %s", target)
            details["error"] = str(exc)
            write_audit_log(
                current_app,
                "order_delete_folder_failed",
                user=current_user,
                level="error",
                details=details,
                log_file=DELETE_LOG_FILE,
            )
        return details

    def _delete_order_files(order_id: int) -> list[dict[str, object]]:
        results = []
        write_audit_log(
            current_app,
            "order_delete_files_started",
            user=current_user,
            details={"order_id": order_id},
            log_file=DELETE_LOG_FILE,
        )
        for config_key in (
            "UPLOAD_FOLDER",
            "IMAGE_UPLOAD_FOLDER",
            "GCODE_UPLOAD_FOLDER",
            "POSTER_UPLOAD_FOLDER",
            "PROCUREMENT_NOTE_UPLOAD_FOLDER",
        ):
            results.append(_remove_order_upload_folder(config_key, order_id))
        errors = [result for result in results if result.get("error")]
        if errors:
            raise RuntimeError(f"File deletion failed for order {order_id}: {errors}")
        return results

    def _delete_order_from_database(order: Order) -> dict[str, int]:
        order_id = order.id
        deleted_counts = {
            "order_read_status": OrderReadStatus.query.filter_by(order_id=order_id).delete(synchronize_session=False),
            "order_messages": OrderMessage.query.filter_by(order_id=order_id).delete(synchronize_session=False),
            "order_files": OrderFile.query.filter_by(order_id=order_id).delete(synchronize_session=False),
            "order_images": OrderImage.query.filter_by(order_id=order_id).delete(synchronize_session=False),
            "order_poster_files": OrderPosterFile.query.filter_by(order_id=order_id).delete(synchronize_session=False),
            "order_procurement_articles": OrderProcurementArticle.query.filter_by(order_id=order_id).delete(synchronize_session=False),
            "order_print_jobs": OrderPrintJob.query.filter_by(order_id=order_id).delete(synchronize_session=False),
            "order_tags": OrderTag.query.filter_by(order_id=order_id).delete(synchronize_session=False),
        }
        db.session.delete(order)
        return deleted_counts

    def normalize_youtube_url(raw_url: str) -> tuple[bool, str]:
        """
        Leichtgewichtige Validierung/Normalisierung f泻r YouTube-Links.
        """
        url = (raw_url or "").strip()
        if not url:
            return False, ""

        candidate = url if "://" in url else f"https://{url}"
        try:
            parsed = urlparse(candidate)
        except Exception:
            return False, candidate

        if parsed.scheme not in ("http", "https"):
            return False, candidate

        host = (parsed.hostname or "").lower()
        allowed_hosts = ("youtube.com", "youtu.be", "youtube-nocookie.com")
        if not any(host.endswith(h) for h in allowed_hosts):
            return False, candidate

        video_id = None
        if host.endswith("youtu.be"):
            path_parts = [p for p in parsed.path.split("/") if p]
            video_id = path_parts[0] if path_parts else None
        elif host.endswith("youtube.com") or host.endswith("youtube-nocookie.com"):
            qs = parse_qs(parsed.query)
            video_id = qs.get("v", [None])[0]
            if not video_id:
                path_parts = [p for p in parsed.path.split("/") if p]
                if len(path_parts) >= 2 and path_parts[0] == "embed":
                    video_id = path_parts[1]
                elif len(path_parts) >= 2 and path_parts[0] == "shorts":
                    video_id = path_parts[1]

        if not video_id:
            return False, candidate

        normalized = f"https://www.youtube.com/watch?v={video_id}"
        return True, normalized

    # Admin Panel / Settings -------------------------------------------------

    @bp.route("/", endpoint="admin_panel")
    @roles_required("admin")
    def admin_panel():
        """Einfache Admin-Startseite."""
        return render_template("admin.html")

    @bp.route("/design-smoke-test", endpoint="admin_design_smoke_test")
    @roles_required("admin")
    def admin_design_smoke_test():
        """Visual smoke-test page for contrast-sensitive UI components."""
        return render_template("admin_design_smoke_test.html")

    @bp.route("/3d-print-master-data", endpoint="admin_3d_print_master_data")
    @roles_required("admin")
    def admin_3d_print_master_data():
        """Grouped master data area for 3D printing."""
        return render_template("admin_3d_print_master_data.html")

    @bp.route("/orders", endpoint="admin_orders")
    @roles_required("admin")
    def admin_orders():
        """Admin order archive/delete management."""
        orders = (
            Order.query
            .order_by(Order.is_archived.asc(), Order.created_at.desc(), Order.id.desc())
            .all()
        )
        order_ids = [order.id for order in orders]
        print_job_counts = {}
        if order_ids:
            print_job_rows = (
                db.session.query(
                    OrderPrintJob.order_id,
                    OrderPrintJob.status,
                    func.count(OrderPrintJob.id),
                )
                .filter(OrderPrintJob.order_id.in_(order_ids))
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

        return render_template("admin_orders.html", orders=orders, print_job_counts=print_job_counts)

    @bp.route("/orders/<int:order_id>/archive", methods=["POST"], endpoint="admin_order_archive")
    @roles_required("admin")
    def admin_order_archive(order_id: int):
        trans = t
        order = Order.query.get_or_404(order_id)
        if not order.is_archived:
            order.is_archived = True
            order.archived_at = datetime.utcnow()
            db.session.commit()
            write_audit_log(
                current_app,
                "order_archived",
                user=current_user,
                details={"order_id": order.id, "title": order.title},
            )
            flash(trans("flash_order_archived"), "info")
        else:
            flash(trans("flash_order_already_archived"), "warning")
        return redirect(url_for(".admin_orders"))

    @bp.route("/orders/<int:order_id>/delete", methods=["POST"], endpoint="admin_order_delete")
    @roles_required("admin")
    def admin_order_delete(order_id: int):
        trans = t
        order = Order.query.get_or_404(order_id)
        order_title = order.title
        try:
            write_audit_log(
                current_app,
                "order_delete_requested",
                user=current_user,
                details={"order_id": order_id, "title": order_title, "is_archived": bool(order.is_archived)},
                log_file=DELETE_LOG_FILE,
            )
            file_delete_results = _delete_order_files(order.id)
            write_audit_log(
                current_app,
                "order_delete_database_started",
                user=current_user,
                details={"order_id": order_id, "title": order_title},
                log_file=DELETE_LOG_FILE,
            )
            deleted_counts = _delete_order_from_database(order)
            db.session.commit()
            write_audit_log(
                current_app,
                "order_deleted",
                user=current_user,
                details={"order_id": order_id, "title": order_title},
            )
            write_audit_log(
                current_app,
                "order_delete_completed",
                user=current_user,
                details={
                    "order_id": order_id,
                    "title": order_title,
                    "deleted_counts": deleted_counts,
                    "file_delete_results": file_delete_results,
                },
                log_file=DELETE_LOG_FILE,
            )
            flash(trans("flash_order_deleted"), "info")
        except Exception as exc:
            db.session.rollback()
            current_app.logger.exception("Failed to delete order %s", order_id)
            write_audit_log(
                current_app,
                "order_delete_failed",
                user=current_user,
                level="error",
                details={"order_id": order_id, "title": order_title, "error": str(exc)},
            )
            write_audit_log(
                current_app,
                "order_delete_failed",
                user=current_user,
                level="error",
                details={"order_id": order_id, "title": order_title, "error": str(exc)},
                log_file=DELETE_LOG_FILE,
            )
            flash(trans("flash_order_delete_failed"), "danger")
        return redirect(url_for(".admin_orders"))

    @bp.route("/settings", methods=["GET", "POST"], endpoint="admin_settings")
    @roles_required("admin")
    def admin_settings():
        """Systemweite Einstellungen (Session-Timeout etc.)."""
        trans = t
        settings = load_app_settings(current_app, force_reload=True)
        active_tab = (request.args.get("tab") or "general").strip().lower()
        if active_tab not in {"general", "email", "status-messages", "legal", "areas"}:
            active_tab = "general"

        if request.method == "POST":
            form_type = request.form.get("form_type", "general")
            active_tab = (request.form.get("active_tab") or active_tab or "general").strip().lower()
            if active_tab not in {"general", "email", "status-messages", "legal", "areas"}:
                active_tab = "general"

            if form_type == "general":
                raw_timeout = (request.form.get("session_timeout_minutes") or "").strip()
                timeout_value = coerce_positive_int(raw_timeout, None)
                rows_value = coerce_dashboard_rows_per_page(request.form.get("dashboard_rows_per_page"), None)
                offset_value = coerce_time_display_offset_hours(
                    request.form.get("time_display_offset_hours"),
                    None,
                )
                registration_domain_check_enabled = coerce_bool(
                    request.form.get("registration_domain_check_enabled"),
                    False,
                )
                registration_allowed_domains = serialize_registration_domains(
                    normalize_registration_domains(request.form.get("registration_allowed_domains", ""))
                )

                if timeout_value is None:
                    flash(trans("flash_settings_invalid_timeout"), "danger")
                elif rows_value not in DASHBOARD_ROWS_PER_PAGE_OPTIONS:
                    flash(trans("flash_settings_invalid_dashboard_rows"), "danger")
                elif offset_value is None:
                    flash(trans("flash_settings_invalid_time_display_offset"), "danger")
                elif registration_domain_check_enabled and not registration_allowed_domains:
                    flash(trans("flash_settings_invalid_registration_domains"), "danger")
                else:
                    try:
                        updated_settings = settings.copy()
                        updated_settings["session_timeout_minutes"] = timeout_value
                        updated_settings["dashboard_rows_per_page"] = rows_value
                        updated_settings["time_display_offset_hours"] = offset_value
                        updated_settings["registration_domain_check_enabled"] = registration_domain_check_enabled
                        updated_settings["registration_allowed_domains"] = registration_allowed_domains
                        save_app_settings(current_app, updated_settings)
                        flash(trans("flash_settings_saved"), "success")
                        return redirect(url_for(".admin_settings"))
                    except Exception:
                        current_app.logger.exception("Failed to save admin settings")
                        flash(trans("flash_settings_save_error"), "danger")

            elif form_type == "email":
                smtp_host = (request.form.get("smtp_host") or "").strip()
                smtp_port = coerce_positive_int(request.form.get("smtp_port"), 0)
                smtp_use_tls = bool(request.form.get("smtp_use_tls"))
                smtp_use_ssl = bool(request.form.get("smtp_use_ssl"))
                smtp_user = (request.form.get("smtp_user") or "").strip()
                smtp_password = request.form.get("smtp_password") or ""
                smtp_from_address = (request.form.get("smtp_from_address") or "").strip()

                if not smtp_host or not smtp_port or not smtp_from_address:
                    flash(trans("flash_email_required_fields"), "danger")
                else:
                    try:
                        updated_settings = settings.copy()
                        updated_settings.update(
                            {
                                "smtp_host": smtp_host,
                                "smtp_port": smtp_port,
                                "smtp_use_tls": smtp_use_tls,
                                "smtp_use_ssl": smtp_use_ssl,
                                "smtp_user": smtp_user,
                                "smtp_password": smtp_password,
                                "smtp_from_address": smtp_from_address,
                            }
                        )
                        save_app_settings(current_app, updated_settings)
                        flash(trans("flash_email_settings_saved"), "success")
                        return redirect(url_for(".admin_settings"))
                    except Exception:
                        current_app.logger.exception("Failed to save email settings")
                        flash(trans("flash_settings_save_error"), "danger")

            elif form_type == "email_test":
                test_recipient = (request.form.get("test_email_to") or "").strip()
                if not test_recipient:
                    flash(trans("flash_email_test_recipient_required"), "danger")
                else:
                    try:
                        settings = load_app_settings(current_app, force_reload=True)
                        smtp_host = settings.get("smtp_host")
                        smtp_port = settings.get("smtp_port")
                        smtp_use_tls = bool(settings.get("smtp_use_tls"))
                        smtp_use_ssl = bool(settings.get("smtp_use_ssl"))
                        smtp_user = settings.get("smtp_user")
                        smtp_password = settings.get("smtp_password")
                        smtp_from = settings.get("smtp_from_address")

                        if not smtp_host or not smtp_port or not smtp_from:
                            flash(trans("flash_email_required_fields"), "danger")
                        else:
                            msg = EmailMessage()
                            msg["Subject"] = "NeoFab test email"
                            msg["From"] = smtp_from
                            msg["To"] = test_recipient
                            msg.set_content(
                                "This is a test email from NeoFab. If you received this, SMTP is configured correctly."
                            )

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
                                server.send_message(msg)

                            write_audit_log(
                                current_app,
                                "email_sent",
                                user=current_user,
                                details={
                                    "kind": "smtp_test",
                                    "subject": msg["Subject"],
                                    "recipient_count": 1,
                                    "recipients": [test_recipient],
                                },
                            )

                            flash(trans("flash_email_test_sent").format(recipient=test_recipient), "success")
                    except Exception as exc:
                        current_app.logger.exception("Failed to send test email")
                        flash(trans("flash_email_test_failed").format(error=exc), "danger")
            elif form_type == "email_actions":
                email_actions = {}
                for action_key in EMAIL_ACTION_KEYS:
                    field_value = (request.form.get(f"email_action_{action_key}") or "").strip()
                    if field_value not in (EMAIL_ACTION_STATE_ENABLED, EMAIL_ACTION_STATE_DISABLED):
                        field_value = EMAIL_ACTION_STATE_ENABLED
                    email_actions[action_key] = field_value
                try:
                    updated_settings = settings.copy()
                    updated_settings["email_actions"] = email_actions
                    save_app_settings(current_app, updated_settings)
                    flash(trans("flash_email_actions_saved"), "success")
                    return redirect(url_for(".admin_settings"))
                except Exception:
                    current_app.logger.exception("Failed to save email actions")
                    flash(trans("flash_settings_save_error"), "danger")
            elif form_type == "status_messages":
                allowed_styles = {value for value, _ in STATUS_STYLE_OPTIONS}
                status_messages = {}
                for group_key, defs in STATUS_GROUP_DEFS.items():
                    group_entries = {}
                    for item in defs:
                        status_key = item["key"]
                        label_field = f"status_label_{group_key}_{status_key}"
                        style_field = f"status_style_{group_key}_{status_key}"
                        label_value = (request.form.get(label_field) or "").strip()
                        style_value = (request.form.get(style_field) or "").strip()

                        if style_value not in allowed_styles:
                            style_value = ""

                        default_text = default_label(item, trans)
                        default_style = item.get("style", "")
                        if label_value == default_text:
                            label_value = ""
                        if style_value == default_style:
                            style_value = ""

                        if label_value or style_value:
                            group_entries[status_key] = {"label": label_value, "style": style_value}

                    if group_entries:
                        status_messages[group_key] = group_entries

                try:
                    updated_settings = settings.copy()
                    updated_settings["status_messages"] = status_messages
                    save_app_settings(current_app, updated_settings)
                    flash(trans("flash_status_messages_saved"), "success")
                    return redirect(url_for(".admin_settings"))
                except Exception:
                    current_app.logger.exception("Failed to save status messages")
                    flash(trans("flash_settings_save_error"), "danger")
            elif form_type == "legal":
                imprint_markdown = request.form.get("imprint_markdown") or ""
                privacy_markdown = request.form.get("privacy_markdown") or ""
                welcome_email_texts = {
                    "de": request.form.get("welcome_email_text_de") or "",
                    "en": request.form.get("welcome_email_text_en") or "",
                    "fr": request.form.get("welcome_email_text_fr") or "",
                }

                try:
                    updated_settings = settings.copy()
                    updated_settings["imprint_markdown"] = imprint_markdown
                    updated_settings["privacy_markdown"] = privacy_markdown
                    updated_settings["welcome_email_texts"] = welcome_email_texts
                    save_app_settings(current_app, updated_settings)
                    flash(trans("flash_legal_settings_saved"), "success")
                    return redirect(url_for(".admin_settings"))
                except Exception:
                    current_app.logger.exception("Failed to save legal settings")
                    flash(trans("flash_settings_save_error"), "danger")
            elif form_type == "area_add":
                area_name = (request.form.get("area_name") or "").strip()
                if not area_name:
                    flash(trans("flash_area_required"), "danger")
                else:
                    exists = OrderArea.query.filter(func.lower(OrderArea.name) == area_name.lower()).first()
                    if exists:
                        flash(trans("flash_area_exists"), "danger")
                    else:
                        db.session.add(OrderArea(name=area_name))
                        db.session.commit()
                        flash(trans("flash_area_created"), "success")
                        return redirect(url_for(".admin_settings", tab="areas"))
            elif form_type == "area_update":
                area_id_raw = (request.form.get("area_id") or "").strip()
                area_name = (request.form.get("area_name") or "").strip()
                try:
                    area_id = int(area_id_raw)
                except ValueError:
                    area_id = 0

                area = OrderArea.query.get(area_id) if area_id else None
                if not area:
                    flash(trans("flash_area_not_found"), "warning")
                elif not area_name:
                    flash(trans("flash_area_required"), "danger")
                else:
                    duplicate = OrderArea.query.filter(func.lower(OrderArea.name) == area_name.lower()).first()
                    if duplicate and duplicate.id != area.id:
                        flash(trans("flash_area_exists"), "danger")
                    else:
                        area.name = area_name
                        area.updated_at = datetime.utcnow()
                        db.session.commit()
                        flash(trans("flash_area_updated"), "success")
                        return redirect(url_for(".admin_settings", tab="areas"))
            elif form_type == "area_delete":
                area_id_raw = (request.form.get("area_id") or "").strip()
                try:
                    area_id = int(area_id_raw)
                except ValueError:
                    area_id = 0

                area = OrderArea.query.get(area_id) if area_id else None
                if not area:
                    flash(trans("flash_area_not_found"), "warning")
                else:
                    order_count = Order.query.filter_by(area_id=area.id).count()
                    if order_count > 0:
                        flash(trans("flash_area_delete_in_use"), "danger")
                    else:
                        UserOrderAreaPreference.query.filter_by(area_id=area.id).delete()
                        db.session.delete(area)
                        db.session.commit()
                        flash(trans("flash_area_deleted"), "info")
                        return redirect(url_for(".admin_settings", tab="areas"))

        status_resolved = resolve_status_messages(settings, trans)
        status_groups = []
        group_labels = {
            "order": trans("status_group_orders"),
            "print_job": trans("status_group_print_jobs"),
        }
        for group_key, _defs in STATUS_GROUP_DEFS.items():
            items = []
            for item in status_resolved.get(group_key, []):
                items.append(
                    {
                        **item,
                        "label_name": f"status_label_{group_key}_{item['key']}",
                        "style_name": f"status_style_{group_key}_{item['key']}",
                    }
                )
            status_groups.append(
                {
                    "key": group_key,
                    "label": group_labels.get(group_key, group_key),
                    "items_list": items,
                }
            )

        status_style_options = [
            {"value": value, "label": trans(label_key)}
            for value, label_key in STATUS_STYLE_OPTIONS
        ]
        email_action_values = normalize_email_actions(settings.get("email_actions"))
        email_action_groups = []
        group_labels = {
            "users": trans("email_action_group_users"),
            "orders": trans("email_action_group_orders"),
            "announcements": trans("email_action_group_announcements"),
        }
        for group_key in ("users", "orders", "announcements"):
            items = []
            for item in EMAIL_ACTION_DEFS:
                if item["group"] != group_key:
                    continue
                items.append(
                    {
                        "key": item["key"],
                        "label": trans(f"email_action_{item['key']}"),
                        "description": trans(f"email_action_{item['key']}_desc"),
                        "value": email_action_values.get(item["key"], EMAIL_ACTION_STATE_ENABLED),
                    }
                )
            email_action_groups.append(
                {
                    "key": group_key,
                    "label": group_labels.get(group_key, group_key),
                    "items": items,
                }
            )
        email_action_state_options = [
            {"value": EMAIL_ACTION_STATE_ENABLED, "label": trans("email_action_enabled")},
            {"value": EMAIL_ACTION_STATE_DISABLED, "label": trans("email_action_disabled")},
        ]

        return render_template(
            "admin_settings.html",
            settings=settings,
            settings_path=str(SETTINGS_FILE),
            active_tab=active_tab,
            status_message_groups=status_groups,
            status_style_options=status_style_options,
            email_action_groups=email_action_groups,
            email_action_state_options=email_action_state_options,
            order_areas=OrderArea.query.order_by(OrderArea.name.asc()).all(),
        )

    @bp.route("/areas/export", endpoint="admin_area_export")
    @roles_required("admin")
    def admin_area_export():
        areas = OrderArea.query.order_by(OrderArea.name.asc()).all()
        payload = {
            "version": APP_VERSION,
            "areas": [
                {"name": area.name}
                for area in areas
            ],
        }
        output = json.dumps(payload, ensure_ascii=False, indent=2)
        return current_app.response_class(
            output,
            mimetype="application/json",
            headers={"Content-Disposition": "attachment; filename=NeoFab_areas.json"},
        )

    @bp.route("/areas/import", methods=["POST"], endpoint="admin_area_import")
    @roles_required("admin")
    def admin_area_import():
        trans = t
        file = request.files.get("file")
        if not file or not file.filename:
            flash(trans("flash_json_choose_file"), "warning")
            return redirect(url_for(".admin_settings", tab="areas"))

        try:
            content = file.read().decode("utf-8-sig")
            data = json.loads(content)
        except Exception:
            flash(trans("flash_invalid_json"), "danger")
            return redirect(url_for(".admin_settings", tab="areas"))

        rows = data.get("areas", []) if isinstance(data, dict) else []
        if not isinstance(rows, list):
            flash(trans("flash_invalid_json"), "danger")
            return redirect(url_for(".admin_settings", tab="areas"))

        normalized_names: list[str] = []
        seen_lower: set[str] = set()
        skipped = 0
        for entry in rows:
            name = (entry.get("name") or "").strip() if isinstance(entry, dict) else ""
            key = name.lower()
            if not name or key in seen_lower:
                skipped += 1
                continue
            seen_lower.add(key)
    @bp.route("/logs", endpoint="admin_logs")
    @roles_required("admin")
    def admin_logs():
        """Structured audit log viewer."""
        selected_file = request.args.get("file") or None
        log_files = list_log_files(current_app)
        selected_file, entries = read_log_entries(current_app, selected_file, max_entries=500)
        return render_template(
            "admin_logs.html",
            log_files=log_files,
            selected_file=selected_file,
            entries=entries,
        )

    @bp.route("/logs/delete", methods=["POST"], endpoint="admin_log_delete")
    @roles_required("admin")
    def admin_log_delete():
        """Delete one known log file after UI confirmation."""
        trans = t
        selected_file = (request.form.get("file") or "").strip()
        if selected_file and delete_log_file(current_app, selected_file):
            write_audit_log(
                current_app,
                "log_file_deleted",
                user=current_user,
                details={"file": selected_file},
            )
            flash(trans("flash_log_file_deleted"), "info")
        else:
            flash(trans("flash_log_file_delete_failed"), "danger")
        return redirect(url_for(".admin_logs"))

    @bp.route("/settings/export", endpoint="admin_settings_export")
    @roles_required("admin")
    def admin_settings_export():
        settings = load_app_settings(current_app, force_reload=True)
        resolved = resolve_status_messages(settings, t)
        payload = {
            "version": APP_VERSION,
            "settings": {
                "session_timeout_minutes": settings.get("session_timeout_minutes"),
                "dashboard_rows_per_page": settings.get("dashboard_rows_per_page"),
                "time_display_offset_hours": settings.get("time_display_offset_hours", 0),
                "registration_domain_check_enabled": bool(settings.get("registration_domain_check_enabled")),
                "registration_allowed_domains": settings.get("registration_allowed_domains", ""),
                "smtp_host": settings.get("smtp_host", ""),
                "smtp_port": settings.get("smtp_port", 0),
                "smtp_use_tls": bool(settings.get("smtp_use_tls")),
                "smtp_use_ssl": bool(settings.get("smtp_use_ssl")),
                "smtp_user": settings.get("smtp_user", ""),
                "smtp_password": settings.get("smtp_password", ""),
                "smtp_from_address": settings.get("smtp_from_address", ""),
                "email_actions": normalize_email_actions(settings.get("email_actions")),
                "status_messages": {
                    "order": {
                        item["key"]: {"label": item["label"], "style": item["style"]}
                        for item in resolved.get("order", [])
                    },
                    "print_job": {
                        item["key"]: {"label": item["label"], "style": item["style"]}
                        for item in resolved.get("print_job", [])
                    },
                },
                "imprint_markdown": settings.get("imprint_markdown", ""),
                "privacy_markdown": settings.get("privacy_markdown", ""),
            },
        }
        output = json.dumps(payload, ensure_ascii=False, indent=2)

        return current_app.response_class(
            output,
            mimetype="application/json",
            headers={"Content-Disposition": "attachment; filename=NeoFab_settings.json"},
        )

    @bp.route("/settings/import", methods=["POST"], endpoint="admin_settings_import")
    @roles_required("admin")
    def admin_settings_import():
        trans = t
        file = request.files.get("file")
        if not file or not file.filename:
            flash(trans("flash_json_choose_file"), "warning")
            return redirect(url_for(".admin_settings"))

        try:
            content = file.read().decode("utf-8-sig")
            data = json.loads(content)
        except Exception:
            flash(trans("flash_invalid_json"), "danger")
            return redirect(url_for(".admin_settings"))

        raw = data.get("settings") if isinstance(data, dict) else None
        if raw is None and isinstance(data, dict):
            raw = data

        if not isinstance(raw, dict):
            flash(trans("flash_invalid_json"), "danger")
            return redirect(url_for(".admin_settings"))

        try:
            updated_settings = load_app_settings(current_app, force_reload=True).copy()
            for key in (
                "session_timeout_minutes",
                "dashboard_rows_per_page",
                "time_display_offset_hours",
                "registration_domain_check_enabled",
                "registration_allowed_domains",
                "smtp_host",
                "smtp_port",
                "smtp_use_tls",
                "smtp_use_ssl",
                "smtp_user",
                "smtp_password",
                "smtp_from_address",
                "email_actions",
                "imprint_markdown",
                "privacy_markdown",
            ):
                if key in raw:
                    updated_settings[key] = raw.get(key)

            if "status_messages" in raw:
                updated_settings["status_messages"] = filter_status_messages(raw.get("status_messages"))

            save_app_settings(current_app, updated_settings)
            flash(trans("flash_settings_imported"), "success")
        except Exception:
            current_app.logger.exception("Failed to import settings")
            flash(trans("flash_settings_save_error"), "danger")

        return redirect(url_for(".admin_settings"))

    @bp.route("/announcements", endpoint="admin_announcement_list")
    @roles_required("admin")
    def admin_announcement_list():
        announcements = Announcement.query.order_by(Announcement.created_at.desc(), Announcement.id.desc()).all()
        return render_template(
            "admin_announcements.html",
            announcements=announcements,
            announcement_priority_meta=announcement_priority_meta,
            announcement_form_token=new_admin_announcement_form_token(),
        )

    @bp.route("/announcements/<int:announcement_id>/update", methods=["POST"], endpoint="admin_announcement_update")
    @roles_required("admin")
    def admin_announcement_update(announcement_id):
        trans = t
        if not consume_admin_announcement_form_token():
            return reject_duplicate_admin_announcement_submission()
        announcement = Announcement.query.get_or_404(announcement_id)
        title = (request.form.get("title") or "").strip()
        body = (request.form.get("body") or "").strip()
        priority = (request.form.get("priority") or "info").strip()
        if priority not in announcement_priority_meta:
            priority = "info"

        if not title or not body:
            flash(trans("flash_announcement_required"), "warning")
            return redirect(url_for(".admin_announcement_list"))

        announcement.title = title[:200]
        announcement.body = body
        announcement.priority = priority
        announcement.updated_by_id = current_user.id
        announcement.updated_at = datetime.utcnow()
        AnnouncementRead.query.filter_by(announcement_id=announcement.id).delete()
        db.session.commit()
        flash(trans("flash_announcement_updated"), "success")
        return redirect(url_for(".admin_announcement_list"))

    @bp.route("/announcements/<int:announcement_id>/delete", methods=["POST"], endpoint="admin_announcement_delete")
    @roles_required("admin")
    def admin_announcement_delete(announcement_id):
        trans = t
        announcement = Announcement.query.get_or_404(announcement_id)
        AnnouncementRead.query.filter_by(announcement_id=announcement.id).delete()
        db.session.delete(announcement)
        db.session.commit()
        flash(trans("flash_announcement_deleted"), "info")
        return redirect(url_for(".admin_announcement_list"))

    @bp.route("/announcements/export", endpoint="admin_announcement_export")
    @roles_required("admin")
    def admin_announcement_export():
        announcements = Announcement.query.order_by(Announcement.created_at.asc(), Announcement.id.asc()).all()
        payload = {
            "version": APP_VERSION,
            "announcements": [
                {
                    "title": item.title,
                    "body": item.body,
                    "priority": item.priority or "info",
                    "created_at": item.created_at.isoformat() if item.created_at else None,
                    "updated_at": item.updated_at.isoformat() if item.updated_at else None,
                }
                for item in announcements
            ],
        }
        output = json.dumps(payload, ensure_ascii=False, indent=2)
        return current_app.response_class(
            output,
            mimetype="application/json",
            headers={"Content-Disposition": "attachment; filename=NeoFab_announcements.json"},
        )

    @bp.route("/announcements/import", methods=["POST"], endpoint="admin_announcement_import")
    @roles_required("admin")
    def admin_announcement_import():
        trans = t
        file = request.files.get("file")
        if not file or not file.filename:
            flash(trans("flash_json_choose_file"), "warning")
            return redirect(url_for(".admin_announcement_list"))

        try:
            content = file.read().decode("utf-8-sig")
            data = json.loads(content)
        except Exception:
            flash(trans("flash_invalid_json"), "danger")
            return redirect(url_for(".admin_announcement_list"))

        rows = data.get("announcements", []) if isinstance(data, dict) else []
        if not isinstance(rows, list):
            flash(trans("flash_invalid_json"), "danger")
            return redirect(url_for(".admin_announcement_list"))

        AnnouncementRead.query.delete()
        Announcement.query.delete()

        created = skipped = 0
        now = datetime.utcnow()
        for entry in rows:
            if not isinstance(entry, dict):
                skipped += 1
                continue
            title = (entry.get("title") or "").strip()
            body = (entry.get("body") or "").strip()
            priority = (entry.get("priority") or "info").strip()
            if priority not in announcement_priority_meta:
                priority = "info"

            if not title or not body:
                skipped += 1
                continue

            created_at = now
            updated_at = now
            for field_name, target in (("created_at", "created_at"), ("updated_at", "updated_at")):
                raw_date = entry.get(field_name)
                if not raw_date:
                    continue
                try:
                    parsed_date = datetime.fromisoformat(str(raw_date))
                except ValueError:
                    continue
                if target == "created_at":
                    created_at = parsed_date
                else:
                    updated_at = parsed_date

            db.session.add(
                Announcement(
                    title=title[:200],
                    body=body,
                    priority=priority,
                    created_at=created_at,
                    updated_at=updated_at,
                    created_by_id=current_user.id,
                    updated_by_id=current_user.id,
                )
            )
            created += 1

        db.session.commit()
        flash(trans("flash_import_result_simple").format(created=created, skipped=skipped), "success")
        return redirect(url_for(".admin_announcement_list"))

    # User Management -------------------------------------------------------

    @bp.route("/users", endpoint="admin_user_list")
    @roles_required("admin")
    def admin_user_list():
        """Übersicht aller User (nur für Admin)."""
        users = User.query.order_by(User.id.asc()).all()
        return render_template("admin_users.html", users=users)

    def _is_last_active_admin(user: User) -> bool:
        if user.role != "admin" or not user.is_active or user.deleted_at is not None:
            return False
        return User.query.filter_by(role="admin", is_active=True, deleted_at=None).count() <= 1

    @bp.route("/users/export", endpoint="admin_user_export")
    @roles_required("admin")
    def admin_user_export():
        """
        Exportiert alle User als JSON (inkl. Passwort-Hash) mit Versionsinfo.
        """
        users = User.query.order_by(User.id.asc()).all()
        payload = {
            "version": APP_VERSION,
            "users": [
                {
                    "email": u.email,
                    "role": u.role,
                    "language": u.language,
                    "salutation": u.salutation or "",
                    "first_name": u.first_name or "",
                    "last_name": u.last_name or "",
                    "address": u.address or "",
                    "position": u.position or "",
                    "cost_center": u.cost_center or "",
                    "study_program": u.study_program or "",
                    "note": u.note or "",
                    "created_at": u.created_at.isoformat() if u.created_at else "",
                    "last_login_at": u.last_login_at.isoformat() if u.last_login_at else "",
                    "is_active": bool(u.is_active),
                    "deleted_at": u.deleted_at.isoformat() if u.deleted_at else "",
                    "password_hash": u.password_hash,
                }
                for u in users
            ],
        }
        output = json.dumps(payload, ensure_ascii=False, indent=2)

        return current_app.response_class(
            output,
            mimetype="application/json",
            headers={"Content-Disposition": "attachment; filename=NeoFab_users.json"},
        )

    @bp.route("/users/import", methods=["POST"], endpoint="admin_user_import")
    @roles_required("admin")
    def admin_user_import():
        """
        Importiert User aus einer JSON-Datei (upsert per Email).
        Bestehende User bleiben erhalten und werden per Email aktualisiert, neue werden angelegt.
        """
        trans = t
        file = request.files.get("file")
        if not file or not file.filename:
            flash(trans("flash_json_choose_file"), "warning")
            return redirect(url_for(".admin_user_list"))

        try:
            content = file.read().decode("utf-8-sig")
            data = json.loads(content)
        except Exception:
            flash(trans("flash_invalid_json"), "danger")
            return redirect(url_for(".admin_user_list"))

        rows = data.get("users", []) if isinstance(data, dict) else []

        created = updated = skipped = 0
        imported_created: list[User] = []
        imported_updated: list[User] = []

        def parse_dt(raw):
            if not raw:
                return None
            try:
                return datetime.fromisoformat(str(raw))
            except Exception:
                return None

        for entry in rows:
            if not isinstance(entry, dict):
                skipped += 1
                continue

            email = (entry.get("email") or "").strip().lower()
            if not email:
                skipped += 1
                continue

            user = User.query.filter_by(email=email).first()
            is_new = False
            if not user:
                user = User(email=email, role="user")
                is_new = True

            user.role = (entry.get("role") or user.role or "user").strip() or "user"
            user.language = (entry.get("language") or user.language or "en").strip() or "en"
            if user.language not in USER_LANGUAGE_VALUES:
                user.language = "en"
            user.is_active = bool(entry.get("is_active", user.is_active if user.id else True))

            user.salutation = (entry.get("salutation") or "").strip() or None
            user.first_name = (entry.get("first_name") or "").strip() or None
            user.last_name = (entry.get("last_name") or "").strip() or None
            user.address = (entry.get("address") or "").strip() or None
            user.position = (entry.get("position") or "").strip() or None
            user.cost_center = (entry.get("cost_center") or "").strip() or None
            user.study_program = (entry.get("study_program") or "").strip() or None
            user.note = (entry.get("note") or "").strip() or None

            created_at = parse_dt(entry.get("created_at"))
            if created_at:
                user.created_at = created_at
            last_login = parse_dt(entry.get("last_login_at"))
            if last_login:
                user.last_login_at = last_login
            user.deleted_at = parse_dt(entry.get("deleted_at"))

            raw_pw_hash = (entry.get("password_hash") or "").strip()
            raw_pw_plain = (entry.get("password") or "").strip()
            if raw_pw_plain:
                user.set_password(raw_pw_plain)
            elif raw_pw_hash:
                user.password_hash = raw_pw_hash
            elif is_new and not user.password_hash:
                user.set_password(secrets.token_urlsafe(12))

            if is_new:
                db.session.add(user)
                imported_created.append(user)
                created += 1
            else:
                imported_updated.append(user)
                updated += 1

        db.session.commit()
        for user in imported_created:
            write_audit_log(
                current_app,
                "user_created",
                user=current_user,
                details={
                    "target_user_id": user.id,
                    "target_email": user.email,
                    "target_role": user.role,
                    "source": "user_import",
                },
            )
            send_user_welcome_notification(current_app, user, source="user_import")
        for user in imported_updated:
            write_audit_log(
                current_app,
                "user_updated",
                user=current_user,
                details={
                    "target_user_id": user.id,
                    "target_email": user.email,
                    "target_role": user.role,
                    "source": "user_import",
                },
            )
        flash(
            trans("flash_import_result_extended").format(
                created=created, updated=updated, skipped=skipped
            ),
            "success",
        )
        return redirect(url_for(".admin_user_list"))

    @bp.route("/users/new-admin", methods=["GET", "POST"], endpoint="admin_user_new_admin")
    @roles_required("admin")
    def admin_user_new_admin():
        """Creates an additional admin user."""
        trans = t
        if request.method == "POST":
            email = request.form.get("email", "").strip().lower()
            password = request.form.get("password", "")
            language = (request.form.get("language") or "en").strip().lower()
            if language not in USER_LANGUAGE_VALUES:
                language = "en"

            if not email:
                flash(trans("flash_email_required"), "danger")
            elif not password:
                flash(trans("flash_password_required"), "danger")
            elif User.query.filter_by(email=email).first():
                flash(trans("flash_user_email_exists"), "danger")
            else:
                user = User(
                    email=email,
                    role="admin",
                    language=language,
                    is_active=True,
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
                write_audit_log(
                    current_app,
                    "user_created",
                    user=current_user,
                    details={
                        "target_user_id": user.id,
                        "target_email": user.email,
                        "target_role": user.role,
                        "source": "admin_new_admin",
                    },
                )
                send_user_welcome_notification(current_app, user, source="admin_new_admin")
                flash(trans("flash_user_created"), "success")
                return redirect(url_for(".admin_user_list"))

        return render_template(
            "admin_user_edit.html",
            user=None,
            is_new_admin=True,
            language_options=USER_LANGUAGE_OPTIONS,
        )

    @bp.route("/users/<int:user_id>/edit", methods=["GET", "POST"], endpoint="admin_user_edit")
    @roles_required("admin")
    def admin_user_edit(user_id):
        """User-Daten bearbeiten (Admin)."""
        user = User.query.get_or_404(user_id)

        if request.method == "POST":
            trans = t
            email = request.form.get("email", "").strip().lower()
            role = request.form.get("role", "user").strip()
            if role not in USER_ROLE_VALUES:
                role = "user"
            language = (request.form.get("language") or user.language or "en").strip().lower()
            if language not in USER_LANGUAGE_VALUES:
                language = "en"
            new_password = request.form.get("password", "")

            salutation = request.form.get("salutation") or None
            first_name = request.form.get("first_name") or None
            last_name = request.form.get("last_name") or None
            address = request.form.get("address") or None
            position = request.form.get("position") or None
            cost_center = request.form.get("cost_center") or None
            study_program = request.form.get("study_program") or None
            note = request.form.get("note") or None
            is_active = bool(request.form.get("is_active"))

            if not email:
                flash(trans("flash_email_required"), "danger")
            else:
                existing = User.query.filter_by(email=email).first()
                if existing and existing.id != user.id:
                    flash(trans("flash_user_email_exists"), "danger")
                else:
                    before = {
                        "email": user.email,
                        "role": user.role,
                        "language": user.language,
                        "is_active": bool(user.is_active),
                    }
                    if user.id == current_user.id:
                        is_active = True
                    elif not is_active and _is_last_active_admin(user):
                        flash(trans("flash_last_admin_required"), "danger")
                        return redirect(url_for(".admin_user_edit", user_id=user.id))

                    user.email = email
                    if user.id != current_user.id:
                        user.role = role
                    user.language = language
                    user.is_active = is_active

                    user.salutation = salutation
                    user.first_name = first_name
                    user.last_name = last_name
                    user.address = address
                    user.position = position
                    user.cost_center = cost_center
                    user.study_program = study_program
                    user.note = note

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

                    db.session.commit()
                    write_audit_log(
                        current_app,
                        "user_updated",
                        user=current_user,
                        details={
                            "target_user_id": user.id,
                            "target_email": user.email,
                            "target_role": user.role,
                            "previous_email": before["email"],
                            "previous_role": before["role"],
                            "previous_language": before["language"],
                            "previous_is_active": before["is_active"],
                            "new_language": user.language,
                            "new_is_active": bool(user.is_active),
                            "password_changed": bool(new_password),
                            "source": "admin_user_edit",
                        },
                    )
                    flash(trans("flash_user_updated"), "success")
                    return redirect(url_for(".admin_user_list"))

        worker_categories = OrderCategory.query.filter_by(active=True).order_by(OrderCategory.name.asc()).all()
        selected_worker_category_ids = {
            permission.category_id
            for permission in UserOrderCategoryPermission.query.filter_by(
                user_id=user.id,
                can_manage=True,
            ).all()
        }
        return render_template(
            "admin_user_edit.html",
            user=user,
            role_options=USER_ROLE_OPTIONS,
            language_options=USER_LANGUAGE_OPTIONS,
            worker_categories=worker_categories,
            selected_worker_category_ids=selected_worker_category_ids,
        )

    @bp.route("/users/<int:user_id>/activate", methods=["POST"], endpoint="admin_user_activate")
    @roles_required("admin")
    def admin_user_activate(user_id):
        trans = t
        user = User.query.get_or_404(user_id)
        if user.deleted_at is not None:
            flash(trans("flash_user_deleted_cannot_activate"), "warning")
            return redirect(url_for(".admin_user_list"))

        previous_is_active = bool(user.is_active)
        user.is_active = True
        db.session.commit()
        write_audit_log(
            current_app,
            "user_updated",
            user=current_user,
            details={
                "target_user_id": user.id,
                "target_email": user.email,
                "target_role": user.role,
                "previous_is_active": previous_is_active,
                "new_is_active": bool(user.is_active),
                "status_change": "activated",
                "source": "admin_user_activate",
            },
        )
        flash(trans("flash_user_activated"), "success")
        return redirect(url_for(".admin_user_list"))

    @bp.route("/users/<int:user_id>/deactivate", methods=["POST"], endpoint="admin_user_deactivate")
    @roles_required("admin")
    def admin_user_deactivate(user_id):
        trans = t
        user = User.query.get_or_404(user_id)
        if user.id == current_user.id:
            flash(trans("flash_user_self_status_forbidden"), "danger")
            return redirect(url_for(".admin_user_list"))
        if _is_last_active_admin(user):
            flash(trans("flash_last_admin_required"), "danger")
            return redirect(url_for(".admin_user_list"))

        previous_is_active = bool(user.is_active)
        previous_deleted_at = user.deleted_at.isoformat() if user.deleted_at else None
        user.is_active = False
        db.session.commit()
        write_audit_log(
            current_app,
            "user_updated",
            user=current_user,
            details={
                "target_user_id": user.id,
                "target_email": user.email,
                "target_role": user.role,
                "previous_is_active": previous_is_active,
                "new_is_active": bool(user.is_active),
                "previous_deleted_at": previous_deleted_at,
                "new_deleted_at": user.deleted_at.isoformat() if user.deleted_at else None,
                "status_change": "deactivated",
                "source": "admin_user_deactivate",
            },
        )
        flash(trans("flash_user_deactivated"), "info")
        return redirect(url_for(".admin_user_list"))

    @bp.route("/users/<int:user_id>/delete", methods=["POST"], endpoint="admin_user_delete")
    @roles_required("admin")
    def admin_user_delete(user_id):
        trans = t
        user = User.query.get_or_404(user_id)
        if user.id == current_user.id:
            flash(trans("flash_user_self_status_forbidden"), "danger")
            return redirect(url_for(".admin_user_list"))
        if _is_last_active_admin(user):
            flash(trans("flash_last_admin_required"), "danger")
            return redirect(url_for(".admin_user_list"))

        previous_is_active = bool(user.is_active)
        previous_deleted_at = user.deleted_at.isoformat() if user.deleted_at else None
        user.is_active = False
        user.deleted_at = datetime.utcnow()
        db.session.commit()
        write_audit_log(
            current_app,
            "user_deleted",
            user=current_user,
            details={
                "target_user_id": user.id,
                "target_email": user.email,
                "target_role": user.role,
                "previous_is_active": previous_is_active,
                "new_is_active": bool(user.is_active),
                "previous_deleted_at": previous_deleted_at,
                "new_deleted_at": user.deleted_at.isoformat() if user.deleted_at else None,
                "status_change": "soft_deleted",
                "source": "admin_user_delete",
            },
        )
        flash(trans("flash_user_deleted"), "info")
        return redirect(url_for(".admin_user_list"))

    # Material Master Data --------------------------------------------------

    @bp.route("/materials", endpoint="admin_material_list")
    @roles_required("admin")
    def admin_material_list():
        materials = Material.query.order_by(Material.name.asc()).all()
        return render_template("admin_materials.html", materials=materials)

    @bp.route("/materials/export", endpoint="admin_material_export")
    @roles_required("admin")
    def admin_material_export():
        """Exportiert alle Materialien als JSON (name, description) mit Versionsinfo."""
        materials = Material.query.order_by(Material.name.asc()).all()
        payload = {
            "version": APP_VERSION,
            "materials": [
                {"name": m.name, "description": m.description or ""}
                for m in materials
            ],
        }
        output = json.dumps(payload, ensure_ascii=False, indent=2)

        return current_app.response_class(
            output,
            mimetype="application/json",
            headers={"Content-Disposition": "attachment; filename=NeoFab_materials.json"},
        )

    @bp.route("/materials/import", methods=["POST"], endpoint="admin_material_import")
    @roles_required("admin")
    def admin_material_import():
        """
        Importiert Materialien aus einer JSON-Datei:
        {
          "version": "...",
          "materials": [{ "name": "...", "description": "..." }, ...]
        }
        Bestehende Materialien werden vorher entfernt.
        """
        trans = t
        file = request.files.get("file")
        if not file or not file.filename:
            flash(trans("flash_json_choose_file"), "warning")
            return redirect(url_for(".admin_material_list"))

        try:
            content = file.read().decode("utf-8-sig")
            data = json.loads(content)
        except Exception:
            flash(trans("flash_invalid_json"), "danger")
            return redirect(url_for(".admin_material_list"))

        rows = data.get("materials", []) if isinstance(data, dict) else []

        # Bestehende Materialien vor Import leeren
        Material.query.delete()

        created = skipped = 0
        for entry in rows:
            name = (entry.get("name") or "").strip() if isinstance(entry, dict) else ""
            description = (entry.get("description") or "").strip() if isinstance(entry, dict) else None

            if not name:
                skipped += 1
                continue

            db.session.add(Material(name=name, description=description or None))
            created += 1

        db.session.commit()
        flash(trans("flash_import_result_simple").format(created=created, skipped=skipped), "success")
        return redirect(url_for(".admin_material_list"))

    @bp.route("/materials/new", methods=["GET", "POST"], endpoint="admin_material_new")
    @roles_required("admin")
    def admin_material_new():
        trans = t
        if request.method == "POST":
            name = request.form.get("name", "").strip()
            description = request.form.get("description", "").strip() or None

            if not name:
                flash(trans("flash_material_required"), "danger")
            else:
                existing = Material.query.filter_by(name=name).first()
                if existing:
                    flash(trans("flash_material_exists"), "danger")
                else:
                    m = Material(name=name, description=description)
                    db.session.add(m)
                    db.session.commit()
                    flash(trans("flash_material_created"), "success")
                    return redirect(url_for(".admin_material_list"))

        return render_template("admin_material_edit.html", material=None)

    @bp.route("/materials/<int:material_id>/edit", methods=["GET", "POST"], endpoint="admin_material_edit")
    @roles_required("admin")
    def admin_material_edit(material_id):
        trans = t
        material = Material.query.get_or_404(material_id)

        if request.method == "POST":
            name = request.form.get("name", "").strip()
            description = request.form.get("description", "").strip() or None

            if not name:
                flash(trans("flash_material_required"), "danger")
            else:
                existing = Material.query.filter_by(name=name).first()
                if existing and existing.id != material.id:
                    flash(trans("flash_material_exists"), "danger")
                else:
                    material.name = name
                    material.description = description
                    db.session.commit()
                    flash(trans("flash_material_updated"), "success")
                    return redirect(url_for(".admin_material_list"))

        return render_template("admin_material_edit.html", material=material)

    @bp.route("/materials/<int:material_id>/delete", methods=["POST"], endpoint="admin_material_delete")
    @roles_required("admin")
    def admin_material_delete(material_id):
        trans = t
        material = Material.query.get_or_404(material_id)
        db.session.delete(material)
        db.session.commit()
        flash(trans("flash_material_deleted"), "info")
        return redirect(url_for(".admin_material_list"))

    # Printer Profiles -----------------------------------------------------

    @bp.route("/printer-profiles", endpoint="admin_printer_profile_list")
    @roles_required("admin")
    def admin_printer_profile_list():
        profiles = PrinterProfile.query.order_by(PrinterProfile.name.asc()).all()
        return render_template("admin_printer_profiles.html", profiles=profiles)

    @bp.route("/printer-profiles/export", endpoint="admin_printer_profile_export")
    @roles_required("admin")
    def admin_printer_profile_export():
        """Exportiert alle Drucker-Typen als JSON mit Versionsinfo."""
        profiles = PrinterProfile.query.order_by(PrinterProfile.name.asc()).all()
        payload = {
            "version": APP_VERSION,
            "printer_profiles": [
                {
                    "name": p.name,
                    "description": p.description or "",
                    "time_factor": p.time_factor,
                    "time_offset_min": p.time_offset_min,
                    "machine_hourly_rate": p.machine_hourly_rate,
                    "maintenance_hourly_rate": p.maintenance_hourly_rate,
                    "setup_fee": p.setup_fee,
                    "active": bool(p.active),
                }
                for p in profiles
            ],
        }
        output = json.dumps(payload, ensure_ascii=False, indent=2)

        return current_app.response_class(
            output,
            mimetype="application/json",
            headers={"Content-Disposition": "attachment; filename=NeoFab_printer_profiles.json"},
        )

    @bp.route("/printer-profiles/import", methods=["POST"], endpoint="admin_printer_profile_import")
    @roles_required("admin")
    def admin_printer_profile_import():
        """
        Importiert Drucker-Typen aus einer JSON-Datei.
        Bestehende Drucker-Typen werden vorher entfernt.
        """
        trans = t
        file = request.files.get("file")
        if not file or not file.filename:
            flash(trans("flash_json_choose_file"), "warning")
            return redirect(url_for(".admin_printer_profile_list"))

        try:
            content = file.read().decode("utf-8-sig")
            data = json.loads(content)
        except Exception:
            flash(trans("flash_invalid_json"), "danger")
            return redirect(url_for(".admin_printer_profile_list"))

        rows = data.get("printer_profiles", []) if isinstance(data, dict) else []

        PrinterProfile.query.delete()
        created = skipped = 0
        for entry in rows:
            if not isinstance(entry, dict):
                skipped += 1
                continue

            name = (entry.get("name") or "").strip()
            description = (entry.get("description") or "").strip() or None
            time_factor = _parse_nonnegative_float(entry.get("time_factor"), 1.0)
            time_offset_min_raw = entry.get("time_offset_min", 0)
            machine_hourly_rate = _parse_nonnegative_float(entry.get("machine_hourly_rate"), 0.0)
            maintenance_hourly_rate = _parse_nonnegative_float(entry.get("maintenance_hourly_rate"), 0.0)
            setup_fee = _parse_nonnegative_float(entry.get("setup_fee"), 0.0)
            try:
                time_offset_min = int(time_offset_min_raw)
            except (TypeError, ValueError):
                time_offset_min = None

            if (
                not name
                or time_factor is None
                or time_factor < 1.0
                or time_offset_min is None
                or time_offset_min < 0
                or machine_hourly_rate is None
                or maintenance_hourly_rate is None
                or setup_fee is None
            ):
                skipped += 1
                continue

            db.session.add(
                PrinterProfile(
                    name=name,
                    description=description,
                    time_factor=time_factor,
                    time_offset_min=time_offset_min,
                    machine_hourly_rate=machine_hourly_rate,
                    maintenance_hourly_rate=maintenance_hourly_rate,
                    setup_fee=setup_fee,
                    active=_parse_bool(entry.get("active"), True),
                )
            )
            created += 1

        db.session.commit()
        flash(trans("flash_import_result_simple").format(created=created, skipped=skipped), "success")
        return redirect(url_for(".admin_printer_profile_list"))

    @bp.route("/printer-profiles/new", methods=["GET", "POST"], endpoint="admin_printer_profile_new")
    @roles_required("admin")
    def admin_printer_profile_new():
        trans = t

        def parse_nonnegative_float(raw_value):
            try:
                value = float((raw_value or "").replace(",", "."))
            except ValueError:
                return None
            return value if value >= 0 else None

        if request.method == "POST":
            name = request.form.get("name", "").strip()
            description = request.form.get("description", "").strip() or None
            time_factor_raw = request.form.get("time_factor", "").strip()
            time_offset_raw = request.form.get("time_offset_min", "").strip()
            machine_hourly_rate_raw = request.form.get("machine_hourly_rate", "").strip()
            maintenance_hourly_rate_raw = request.form.get("maintenance_hourly_rate", "").strip()
            setup_fee_raw = request.form.get("setup_fee", "").strip()
            is_active = bool(request.form.get("is_active"))

            has_errors = False

            if not name:
                flash(trans("flash_printer_profile_required"), "danger")
                has_errors = True
            else:
                existing = PrinterProfile.query.filter(
                    func.lower(PrinterProfile.name) == name.lower()
                ).first()
                if existing:
                    flash(trans("flash_printer_profile_exists"), "danger")
                    has_errors = True

            try:
                time_factor = float(time_factor_raw)
            except ValueError:
                time_factor = None
            if time_factor is None or time_factor < 1.0:
                flash(trans("flash_printer_profile_factor_invalid"), "danger")
                has_errors = True

            try:
                time_offset_min = int(time_offset_raw)
            except ValueError:
                time_offset_min = None
            if time_offset_min is None or time_offset_min < 0:
                flash(trans("flash_printer_profile_offset_invalid"), "danger")
                has_errors = True

            machine_hourly_rate = parse_nonnegative_float(machine_hourly_rate_raw or "0")
            maintenance_hourly_rate = parse_nonnegative_float(maintenance_hourly_rate_raw or "0")
            setup_fee = parse_nonnegative_float(setup_fee_raw or "0")
            if machine_hourly_rate is None or maintenance_hourly_rate is None or setup_fee is None:
                flash(trans("flash_printer_profile_costs_invalid"), "danger")
                has_errors = True

            if not has_errors:
                profile = PrinterProfile(
                    name=name,
                    description=description,
                    time_factor=time_factor,
                    time_offset_min=time_offset_min,
                    machine_hourly_rate=machine_hourly_rate,
                    maintenance_hourly_rate=maintenance_hourly_rate,
                    setup_fee=setup_fee,
                    active=is_active,
                )
                db.session.add(profile)
                db.session.commit()
                flash(trans("flash_printer_profile_created"), "success")
                return redirect(url_for(".admin_printer_profile_list"))

        return render_template("admin_printer_profile_edit.html", profile=None)

    @bp.route("/printer-profiles/<int:profile_id>/edit", methods=["GET", "POST"], endpoint="admin_printer_profile_edit")
    @roles_required("admin")
    def admin_printer_profile_edit(profile_id):
        trans = t
        profile = PrinterProfile.query.get_or_404(profile_id)

        def parse_nonnegative_float(raw_value):
            try:
                value = float((raw_value or "").replace(",", "."))
            except ValueError:
                return None
            return value if value >= 0 else None

        if request.method == "POST":
            name = request.form.get("name", "").strip()
            description = request.form.get("description", "").strip() or None
            time_factor_raw = request.form.get("time_factor", "").strip()
            time_offset_raw = request.form.get("time_offset_min", "").strip()
            machine_hourly_rate_raw = request.form.get("machine_hourly_rate", "").strip()
            maintenance_hourly_rate_raw = request.form.get("maintenance_hourly_rate", "").strip()
            setup_fee_raw = request.form.get("setup_fee", "").strip()
            is_active = bool(request.form.get("is_active"))

            has_errors = False

            if not name:
                flash(trans("flash_printer_profile_required"), "danger")
                has_errors = True
            else:
                existing = PrinterProfile.query.filter(
                    func.lower(PrinterProfile.name) == name.lower()
                ).first()
                if existing and existing.id != profile.id:
                    flash(trans("flash_printer_profile_exists"), "danger")
                    has_errors = True

            try:
                time_factor = float(time_factor_raw)
            except ValueError:
                time_factor = None
            if time_factor is None or time_factor < 1.0:
                flash(trans("flash_printer_profile_factor_invalid"), "danger")
                has_errors = True

            try:
                time_offset_min = int(time_offset_raw)
            except ValueError:
                time_offset_min = None
            if time_offset_min is None or time_offset_min < 0:
                flash(trans("flash_printer_profile_offset_invalid"), "danger")
                has_errors = True

            machine_hourly_rate = parse_nonnegative_float(machine_hourly_rate_raw or "0")
            maintenance_hourly_rate = parse_nonnegative_float(maintenance_hourly_rate_raw or "0")
            setup_fee = parse_nonnegative_float(setup_fee_raw or "0")
            if machine_hourly_rate is None or maintenance_hourly_rate is None or setup_fee is None:
                flash(trans("flash_printer_profile_costs_invalid"), "danger")
                has_errors = True

            if not has_errors:
                profile.name = name
                profile.description = description
                profile.time_factor = time_factor
                profile.time_offset_min = time_offset_min
                profile.machine_hourly_rate = machine_hourly_rate
                profile.maintenance_hourly_rate = maintenance_hourly_rate
                profile.setup_fee = setup_fee
                profile.active = is_active
                db.session.commit()
                flash(trans("flash_printer_profile_updated"), "success")
                return redirect(url_for(".admin_printer_profile_list"))

        return render_template("admin_printer_profile_edit.html", profile=profile)

    @bp.route("/printer-profiles/<int:profile_id>/delete", methods=["POST"], endpoint="admin_printer_profile_delete")
    @roles_required("admin")
    def admin_printer_profile_delete(profile_id):
        trans = t
        profile = PrinterProfile.query.get_or_404(profile_id)
        db.session.delete(profile)
        db.session.commit()
        flash(trans("flash_printer_profile_deleted"), "info")
        return redirect(url_for(".admin_printer_profile_list"))

    # Filament Materials ---------------------------------------------------

    @bp.route("/filament-materials", endpoint="admin_filament_material_list")
    @roles_required("admin")
    def admin_filament_material_list():
        materials = FilamentMaterial.query.order_by(FilamentMaterial.name.asc()).all()
        return render_template("admin_filament_materials.html", materials=materials)

    @bp.route("/filament-materials/export", endpoint="admin_filament_material_export")
    @roles_required("admin")
    def admin_filament_material_export():
        """Exportiert alle Filament-Materialien als JSON mit Versionsinfo."""
        materials = FilamentMaterial.query.order_by(FilamentMaterial.name.asc()).all()
        payload = {
            "version": APP_VERSION,
            "filament_materials": [
                {
                    "name": m.name,
                    "description": m.description or "",
                    "filament_diameter_mm": m.filament_diameter_mm,
                    "density_g_cm3": m.density_g_cm3,
                    "price_per_kg": m.price_per_kg,
                    "markup_percent": m.markup_percent,
                    "drying_fee": m.drying_fee,
                    "handling_fee": m.handling_fee,
                    "active": bool(m.active),
                }
                for m in materials
            ],
        }
        output = json.dumps(payload, ensure_ascii=False, indent=2)

        return current_app.response_class(
            output,
            mimetype="application/json",
            headers={"Content-Disposition": "attachment; filename=NeoFab_filament_materials.json"},
        )

    @bp.route("/filament-materials/import", methods=["POST"], endpoint="admin_filament_material_import")
    @roles_required("admin")
    def admin_filament_material_import():
        """
        Importiert Filament-Materialien aus einer JSON-Datei.
        Bestehende Filament-Materialien werden vorher entfernt.
        """
        trans = t
        file = request.files.get("file")
        if not file or not file.filename:
            flash(trans("flash_json_choose_file"), "warning")
            return redirect(url_for(".admin_filament_material_list"))

        try:
            content = file.read().decode("utf-8-sig")
            data = json.loads(content)
        except Exception:
            flash(trans("flash_invalid_json"), "danger")
            return redirect(url_for(".admin_filament_material_list"))

        rows = data.get("filament_materials", []) if isinstance(data, dict) else []

        FilamentMaterial.query.delete()
        created = skipped = 0
        for entry in rows:
            if not isinstance(entry, dict):
                skipped += 1
                continue

            name = (entry.get("name") or "").strip()
            description = (entry.get("description") or "").strip() or None
            filament_diameter_mm = _parse_nonnegative_float(entry.get("filament_diameter_mm"), 1.75)
            density_g_cm3 = _parse_nonnegative_float(entry.get("density_g_cm3"), None)
            price_per_kg = _parse_nonnegative_float(entry.get("price_per_kg"), 0.0)
            markup_percent = _parse_nonnegative_float(entry.get("markup_percent"), 0.0)
            drying_fee = _parse_nonnegative_float(entry.get("drying_fee"), 0.0)
            handling_fee = _parse_nonnegative_float(entry.get("handling_fee"), 0.0)

            if (
                not name
                or filament_diameter_mm is None
                or filament_diameter_mm <= 0
                or density_g_cm3 is None
                or density_g_cm3 <= 0
                or price_per_kg is None
                or markup_percent is None
                or drying_fee is None
                or handling_fee is None
            ):
                skipped += 1
                continue

            db.session.add(
                FilamentMaterial(
                    name=name,
                    description=description,
                    filament_diameter_mm=filament_diameter_mm,
                    density_g_cm3=density_g_cm3,
                    price_per_kg=price_per_kg,
                    markup_percent=markup_percent,
                    drying_fee=drying_fee,
                    handling_fee=handling_fee,
                    active=_parse_bool(entry.get("active"), True),
                )
            )
            created += 1

        db.session.commit()
        flash(trans("flash_import_result_simple").format(created=created, skipped=skipped), "success")
        return redirect(url_for(".admin_filament_material_list"))

    @bp.route("/filament-materials/new", methods=["GET", "POST"], endpoint="admin_filament_material_new")
    @roles_required("admin")
    def admin_filament_material_new():
        trans = t
        if request.method == "POST":
            name = request.form.get("name", "").strip()
            description = request.form.get("description", "").strip() or None
            diameter_raw = request.form.get("filament_diameter_mm", "").strip()
            density_raw = request.form.get("density_g_cm3", "").strip()
            price_per_kg = _parse_nonnegative_float(request.form.get("price_per_kg"), 0.0)
            markup_percent = _parse_nonnegative_float(request.form.get("markup_percent"), 0.0)
            drying_fee = _parse_nonnegative_float(request.form.get("drying_fee"), 0.0)
            handling_fee = _parse_nonnegative_float(request.form.get("handling_fee"), 0.0)
            is_active = bool(request.form.get("is_active"))

            has_errors = False

            if not name:
                flash(trans("flash_filament_material_required"), "danger")
                has_errors = True
            else:
                existing = FilamentMaterial.query.filter(
                    func.lower(FilamentMaterial.name) == name.lower()
                ).first()
                if existing:
                    flash(trans("flash_filament_material_exists"), "danger")
                    has_errors = True

            try:
                filament_diameter_mm = float(diameter_raw)
            except ValueError:
                filament_diameter_mm = None
            if filament_diameter_mm is None or filament_diameter_mm <= 0:
                flash(trans("flash_filament_material_diameter_invalid"), "danger")
                has_errors = True

            try:
                density_g_cm3 = float(density_raw)
            except ValueError:
                density_g_cm3 = None
            if density_g_cm3 is None or density_g_cm3 <= 0:
                flash(trans("flash_filament_material_density_invalid"), "danger")
                has_errors = True
            if None in (price_per_kg, markup_percent, drying_fee, handling_fee):
                flash(trans("flash_filament_material_costs_invalid"), "danger")
                has_errors = True

            if not has_errors:
                material = FilamentMaterial(
                    name=name,
                    description=description,
                    filament_diameter_mm=filament_diameter_mm,
                    density_g_cm3=density_g_cm3,
                    price_per_kg=price_per_kg,
                    markup_percent=markup_percent,
                    drying_fee=drying_fee,
                    handling_fee=handling_fee,
                    active=is_active,
                )
                db.session.add(material)
                db.session.commit()
                flash(trans("flash_filament_material_created"), "success")
                return redirect(url_for(".admin_filament_material_list"))

        return render_template("admin_filament_material_edit.html", material=None)

    @bp.route(
        "/filament-materials/<int:material_id>/edit",
        methods=["GET", "POST"],
        endpoint="admin_filament_material_edit",
    )
    @roles_required("admin")
    def admin_filament_material_edit(material_id):
        trans = t
        material = FilamentMaterial.query.get_or_404(material_id)

        if request.method == "POST":
            name = request.form.get("name", "").strip()
            description = request.form.get("description", "").strip() or None
            diameter_raw = request.form.get("filament_diameter_mm", "").strip()
            density_raw = request.form.get("density_g_cm3", "").strip()
            price_per_kg = _parse_nonnegative_float(request.form.get("price_per_kg"), 0.0)
            markup_percent = _parse_nonnegative_float(request.form.get("markup_percent"), 0.0)
            drying_fee = _parse_nonnegative_float(request.form.get("drying_fee"), 0.0)
            handling_fee = _parse_nonnegative_float(request.form.get("handling_fee"), 0.0)
            is_active = bool(request.form.get("is_active"))

            has_errors = False

            if not name:
                flash(trans("flash_filament_material_required"), "danger")
                has_errors = True
            else:
                existing = FilamentMaterial.query.filter(
                    func.lower(FilamentMaterial.name) == name.lower()
                ).first()
                if existing and existing.id != material.id:
                    flash(trans("flash_filament_material_exists"), "danger")
                    has_errors = True

            try:
                filament_diameter_mm = float(diameter_raw)
            except ValueError:
                filament_diameter_mm = None
            if filament_diameter_mm is None or filament_diameter_mm <= 0:
                flash(trans("flash_filament_material_diameter_invalid"), "danger")
                has_errors = True

            try:
                density_g_cm3 = float(density_raw)
            except ValueError:
                density_g_cm3 = None
            if density_g_cm3 is None or density_g_cm3 <= 0:
                flash(trans("flash_filament_material_density_invalid"), "danger")
                has_errors = True
            if None in (price_per_kg, markup_percent, drying_fee, handling_fee):
                flash(trans("flash_filament_material_costs_invalid"), "danger")
                has_errors = True

            if not has_errors:
                material.name = name
                material.description = description
                material.filament_diameter_mm = filament_diameter_mm
                material.density_g_cm3 = density_g_cm3
                material.price_per_kg = price_per_kg
                material.markup_percent = markup_percent
                material.drying_fee = drying_fee
                material.handling_fee = handling_fee
                material.active = is_active
                db.session.commit()
                flash(trans("flash_filament_material_updated"), "success")
                return redirect(url_for(".admin_filament_material_list"))

        return render_template("admin_filament_material_edit.html", material=material)

    @bp.route("/filament-materials/<int:material_id>/delete", methods=["POST"], endpoint="admin_filament_material_delete")
    @roles_required("admin")
    def admin_filament_material_delete(material_id):
        trans = t
        material = FilamentMaterial.query.get_or_404(material_id)
        db.session.delete(material)
        db.session.commit()
        flash(trans("flash_filament_material_deleted"), "info")
        return redirect(url_for(".admin_filament_material_list"))

    # Color Master Data -----------------------------------------------------

    @bp.route("/colors", endpoint="admin_color_list")
    @roles_required("admin")
    def admin_color_list():
        colors = Color.query.order_by(Color.name.asc()).all()
        return render_template("admin_colors.html", colors=colors)

    @bp.route("/colors/export", endpoint="admin_color_export")
    @roles_required("admin")
    def admin_color_export():
        """Exportiert alle Farben als JSON (name, hex_code) mit Versionsinfo."""
        colors = Color.query.order_by(Color.name.asc()).all()
        payload = {
            "version": APP_VERSION,
            "colors": [
                {"name": c.name, "hex_code": c.hex_code or ""}
                for c in colors
            ],
        }
        output = json.dumps(payload, ensure_ascii=False, indent=2)

        return current_app.response_class(
            output,
            mimetype="application/json",
            headers={"Content-Disposition": "attachment; filename=NeoFab_colors.json"},
        )

    @bp.route("/colors/import", methods=["POST"], endpoint="admin_color_import")
    @roles_required("admin")
    def admin_color_import():
        """
        Importiert Farben aus einer JSON-Datei:
        {
          "version": "...",
          "colors": [{ "name": "...", "hex_code": "#RRGGBB" }, ...]
        }
        Bestehende Namen werden aktualisiert, neue angelegt.
        """
        trans = t
        file = request.files.get("file")
        if not file or not file.filename:
            flash(trans("flash_json_choose_file"), "warning")
            return redirect(url_for(".admin_color_list"))

        try:
            content = file.read().decode("utf-8-sig")
            data = json.loads(content)
        except Exception:
            flash(trans("flash_invalid_json"), "danger")
            return redirect(url_for(".admin_color_list"))

        rows = data.get("colors", []) if isinstance(data, dict) else []

        # Bestehende Farben vor Import leeren
        Color.query.delete()
        created = updated = skipped = 0
        for entry in rows:
            name = (entry.get("name") or "").strip() if isinstance(entry, dict) else ""
            hex_code = (entry.get("hex_code") or "").strip() if isinstance(entry, dict) else None

            if not name:
                skipped += 1
                continue

            color = Color.query.filter_by(name=name).first()
            if color:
                color.hex_code = hex_code or None
                updated += 1
            else:
                db.session.add(Color(name=name, hex_code=hex_code or None))
                created += 1

        db.session.commit()
        flash(
            trans("flash_import_result_extended").format(
                created=created, updated=updated, skipped=skipped
            ),
            "success",
        )
        return redirect(url_for(".admin_color_list"))

    @bp.route("/colors/new", methods=["GET", "POST"], endpoint="admin_color_new")
    @roles_required("admin")
    def admin_color_new():
        trans = t
        if request.method == "POST":
            name = request.form.get("name", "").strip()
            hex_code = request.form.get("hex_code", "").strip() or None

            if not name:
                flash(trans("flash_color_required"), "danger")
            else:
                existing = Color.query.filter_by(name=name).first()
                if existing:
                    flash(trans("flash_color_exists"), "danger")
                else:
                    c = Color(name=name, hex_code=hex_code)
                    db.session.add(c)
                    db.session.commit()
                    flash(trans("flash_color_created"), "success")
                    return redirect(url_for(".admin_color_list"))

        return render_template("admin_color_edit.html", color=None)

    @bp.route("/colors/<int:color_id>/edit", methods=["GET", "POST"], endpoint="admin_color_edit")
    @roles_required("admin")
    def admin_color_edit(color_id):
        trans = t
        color = Color.query.get_or_404(color_id)

        if request.method == "POST":
            name = request.form.get("name", "").strip()
            hex_code = request.form.get("hex_code", "").strip() or None

            if not name:
                flash(trans("flash_color_required"), "danger")
            else:
                existing = Color.query.filter_by(name=name).first()
                if existing and existing.id != color.id:
                    flash(trans("flash_color_exists"), "danger")
                else:
                    color.name = name
                    color.hex_code = hex_code
                    db.session.commit()
                    flash(trans("flash_color_updated"), "success")
                    return redirect(url_for(".admin_color_list"))

        return render_template("admin_color_edit.html", color=color)

    @bp.route("/colors/<int:color_id>/delete", methods=["POST"], endpoint="admin_color_delete")
    @roles_required("admin")
    def admin_color_delete(color_id):
        trans = t
        color = Color.query.get_or_404(color_id)
        db.session.delete(color)
        db.session.commit()
        flash(trans("flash_color_deleted"), "info")
        return redirect(url_for(".admin_color_list"))

    # Training Videos (Tutorials) ------------------------------------------

    @bp.route("/training-videos", endpoint="admin_training_video_list")
    @roles_required("admin")
    def admin_training_video_list():
        ensure_training_playlist_schema()
        normalize_training_video_order()
        videos = TrainingVideo.query.order_by(
            TrainingVideo.sort_order.asc(), TrainingVideo.created_at.desc()
        ).all()
        return render_template("admin_training_videos.html", videos=videos)

    @bp.route("/training-playlists", endpoint="admin_training_playlist_list")
    @roles_required("admin")
    def admin_training_playlist_list():
        ensure_training_playlist_schema()
        playlists = TrainingPlaylist.query.order_by(TrainingPlaylist.title.asc()).all()
        return render_template("admin_training_playlists.html", playlists=playlists)

    @bp.route("/training-playlists/new", methods=["GET", "POST"], endpoint="admin_training_playlist_new")
    @roles_required("admin")
    def admin_training_playlist_new():
        trans = t
        ensure_training_playlist_schema()
        if request.method == "POST":
            title = request.form.get("title", "").strip()
            description = request.form.get("description", "").strip() or None
            is_active = bool(request.form.get("active"))

            if not title:
                flash(trans("flash_training_playlist_title_required"), "danger")
            else:
                playlist = TrainingPlaylist(
                    title=title,
                    short_description=description,
                    active=is_active,
                )
                db.session.add(playlist)
                try:
                    db.session.commit()
                except OperationalError as exc:
                    db.session.rollback()
                    if "no such table: training_playlists" in str(exc).lower():
                        db.create_all()
                        db.session.add(playlist)
                        db.session.commit()
                    else:
                        raise
                flash(trans("flash_training_playlist_created"), "success")
                return redirect(url_for(".admin_training_playlist_list"))

        return render_template("admin_training_playlist_edit.html", playlist=None)

    @bp.route("/training-playlists/<int:playlist_id>/edit", methods=["GET", "POST"], endpoint="admin_training_playlist_edit")
    @roles_required("admin")
    def admin_training_playlist_edit(playlist_id):
        trans = t
        ensure_training_playlist_schema()
        playlist = TrainingPlaylist.query.get_or_404(playlist_id)

        if request.method == "POST":
            title = request.form.get("title", "").strip()
            description = request.form.get("description", "").strip() or None
            is_active = bool(request.form.get("active"))

            if not title:
                flash(trans("flash_training_playlist_title_required"), "danger")
            else:
                playlist.title = title
                playlist.short_description = description
                playlist.active = is_active
                playlist.updated_at = datetime.utcnow()
                db.session.commit()
                flash(trans("flash_training_playlist_updated"), "success")
                return redirect(url_for(".admin_training_playlist_list"))

        return render_template("admin_training_playlist_edit.html", playlist=playlist)

    @bp.route("/training-playlists/<int:playlist_id>/delete", methods=["POST"], endpoint="admin_training_playlist_delete")
    @roles_required("admin")
    def admin_training_playlist_delete(playlist_id):
        trans = t
        ensure_training_playlist_schema()
        playlist = TrainingPlaylist.query.get_or_404(playlist_id)
        TrainingVideo.query.filter_by(playlist_id=playlist.id).update({"playlist_id": None})
        db.session.delete(playlist)
        db.session.commit()
        flash(trans("flash_training_playlist_deleted"), "info")
        return redirect(url_for(".admin_training_playlist_list"))

    @bp.route("/training-videos/export", endpoint="admin_training_video_export")
    @roles_required("admin")
    def admin_training_video_export():
        """
        Exportiert alle Trainingsvideos als JSON mit Versionsinfo.
        """
        ensure_training_playlist_schema()
        videos = TrainingVideo.query.order_by(
            TrainingVideo.sort_order.asc(), TrainingVideo.created_at.asc()
        ).all()
        payload = {
            "version": APP_VERSION,
            "training_videos": [
                {
                    "title": v.title,
                    "description": v.description or "",
                    "youtube_url": v.youtube_url,
                    "sort_order": v.sort_order or 0,
                }
                for v in videos
            ],
        }
        output = json.dumps(payload, ensure_ascii=False, indent=2)

        return current_app.response_class(
            output,
            mimetype="application/json",
            headers={
                "Content-Disposition": "attachment; filename=NeoFab_training_videos.json"
            },
        )

    @bp.route("/training-videos/import", methods=["POST"], endpoint="admin_training_video_import")
    @roles_required("admin")
    def admin_training_video_import():
        """
        Importiert Trainingsvideos aus einer JSON-Datei:
        {
          "version": "...",
          "training_videos": [{ "title": "...", "description": "...", "youtube_url": "...", "sort_order": 1 }, ...]
        }
        Bestehende Einträge werden vorher entfernt.
        """
        trans = t
        ensure_training_playlist_schema()
        file = request.files.get("file")
        if not file or not file.filename:
            flash(trans("flash_json_choose_file"), "warning")
            return redirect(url_for(".admin_training_video_list"))

        try:
            content = file.read().decode("utf-8-sig")
            data = json.loads(content)
        except Exception:
            flash(trans("flash_invalid_json"), "danger")
            return redirect(url_for(".admin_training_video_list"))

        rows = data.get("training_videos", []) if isinstance(data, dict) else []

        TrainingVideo.query.delete()

        prepared = []
        created = skipped = 0
        for idx, entry in enumerate(rows, start=1):
            if not isinstance(entry, dict):
                skipped += 1
                continue
            title = (entry.get("title") or "").strip()
            youtube_url = (entry.get("youtube_url") or "").strip()
            description = (entry.get("description") or "").strip() or None
            raw_sort = entry.get("sort_order")
            sort_val = None
            try:
                sort_val = int(raw_sort)
                if sort_val <= 0:
                    sort_val = None
            except Exception:
                sort_val = None

            if not title or not youtube_url:
                skipped += 1
                continue

            order_key = sort_val if sort_val is not None else idx
            prepared.append(
                {
                    "order_key": order_key,
                    "title": title,
                    "description": description,
                    "youtube_url": youtube_url,
                }
            )
            created += 1

        prepared.sort(key=lambda x: (x["order_key"], x["title"].lower()))

        now = datetime.utcnow()
        for pos, item in enumerate(prepared, start=1):
            video = TrainingVideo(
                title=item["title"],
                description=item["description"],
                youtube_url=item["youtube_url"],
                sort_order=pos,
                created_at=now,
                updated_at=now,
            )
            db.session.add(video)

        db.session.commit()
        normalize_training_video_order()
        flash(trans("flash_import_result_simple").format(created=created, skipped=skipped), "success")
        return redirect(url_for(".admin_training_video_list"))

    @bp.route("/training-videos/new", methods=["GET", "POST"], endpoint="admin_training_video_new")
    @roles_required("admin")
    def admin_training_video_new():
        trans = t
        ensure_training_playlist_schema()
        playlists = TrainingPlaylist.query.order_by(TrainingPlaylist.title.asc()).all()
        selected_playlist_id = None
        if request.method == "POST":
            title = request.form.get("title", "").strip()
            description = request.form.get("description", "").strip() or None
            youtube_url = request.form.get("youtube_url", "").strip()
            playlist_id_raw = request.form.get("playlist_id") or ""
            playlist_id = int(playlist_id_raw) if playlist_id_raw.isdigit() else None
            playlist = TrainingPlaylist.query.get(playlist_id) if playlist_id else None
            selected_playlist_id = playlist.id if playlist else None
            pdf_file = request.files.get("pdf_file")
            has_pdf_upload = bool(pdf_file and pdf_file.filename)
            has_youtube = bool(youtube_url)
            normalized_url = ""
            has_errors = False

            if not title:
                flash(trans("flash_training_title_required"), "danger")
                has_errors = True

            if has_youtube:
                is_valid, normalized_url = normalize_youtube_url(youtube_url)
                if not is_valid:
                    flash(trans("flash_training_url_invalid"), "danger")
                    has_errors = True

            if has_pdf_upload:
                safe_name = secure_filename(pdf_file.filename)
                if not safe_name.lower().endswith(".pdf"):
                    flash(trans("flash_training_pdf_invalid"), "danger")
                    has_errors = True

            if not has_youtube and not has_pdf_upload:
                flash(trans("flash_training_source_required"), "danger")
                has_errors = True

            if not has_errors:
                max_order = db.session.query(func.max(TrainingVideo.sort_order)).scalar()
                next_order = (max_order or 0) + 1
                video = TrainingVideo(
                    title=title,
                    description=description,
                    youtube_url=normalized_url or youtube_url if has_youtube else "",
                    sort_order=next_order,
                    playlist_id=playlist.id if playlist else None,
                )
                db.session.add(video)
                db.session.flush()
                if has_pdf_upload:
                    ok, err = _save_training_pdf(video, pdf_file)
                    if not ok:
                        db.session.rollback()
                        if err == "invalid_pdf":
                            flash(trans("flash_training_pdf_invalid"), "danger")
                        else:
                            flash(trans("flash_training_pdf_failed"), "danger")
                        has_errors = True

                if not has_errors:
                    db.session.commit()
                    flash(trans("flash_training_created"), "success")
                    return redirect(url_for(".admin_training_video_list"))
        return render_template(
            "admin_training_video_edit.html",
            video=None,
            playlists=playlists,
            selected_playlist_id=selected_playlist_id,
        )

    @bp.route("/training-videos/<int:video_id>/edit", methods=["GET", "POST"], endpoint="admin_training_video_edit")
    @roles_required("admin")
    def admin_training_video_edit(video_id):
        trans = t
        ensure_training_playlist_schema()
        video = TrainingVideo.query.get_or_404(video_id)
        playlists = TrainingPlaylist.query.order_by(TrainingPlaylist.title.asc()).all()
        selected_playlist_id = video.playlist_id

        if request.method == "POST":
            title = request.form.get("title", "").strip()
            description = request.form.get("description", "").strip() or None
            youtube_url = request.form.get("youtube_url", "").strip()
            playlist_id_raw = request.form.get("playlist_id") or ""
            playlist_id = int(playlist_id_raw) if playlist_id_raw.isdigit() else None
            playlist = TrainingPlaylist.query.get(playlist_id) if playlist_id else None
            selected_playlist_id = playlist.id if playlist else None
            pdf_file = request.files.get("pdf_file")
            remove_pdf = bool(request.form.get("remove_pdf"))
            has_pdf_upload = bool(pdf_file and pdf_file.filename)
            has_existing_pdf = bool(video.pdf_filename)
            has_youtube = bool(youtube_url)
            normalized_url = ""
            has_errors = False

            if not title:
                flash(trans("flash_training_title_required"), "danger")
                has_errors = True

            if has_youtube:
                is_valid, normalized_url = normalize_youtube_url(youtube_url)
                if not is_valid:
                    flash(trans("flash_training_url_invalid"), "danger")
                    has_errors = True

            if has_pdf_upload:
                safe_name = secure_filename(pdf_file.filename)
                if not safe_name.lower().endswith(".pdf"):
                    flash(trans("flash_training_pdf_invalid"), "danger")
                    has_errors = True

            if not has_youtube and not has_pdf_upload and not (has_existing_pdf and not remove_pdf):
                flash(trans("flash_training_source_required"), "danger")
                has_errors = True

            if not has_errors:
                video.title = title
                video.description = description
                video.youtube_url = normalized_url or youtube_url if has_youtube else ""
                video.playlist_id = playlist.id if playlist else None

                if remove_pdf and has_existing_pdf and not has_pdf_upload:
                    _delete_training_pdf(video)
                    video.pdf_filename = None
                    video.pdf_original_name = None
                    video.pdf_filesize = None

                if has_pdf_upload:
                    old_pdf = video.pdf_filename
                    ok, err = _save_training_pdf(video, pdf_file)
                    if not ok:
                        if err == "invalid_pdf":
                            flash(trans("flash_training_pdf_invalid"), "danger")
                        else:
                            flash(trans("flash_training_pdf_failed"), "danger")
                        has_errors = True
                    else:
                        if old_pdf and old_pdf != video.pdf_filename:
                            _delete_training_pdf_by_name(old_pdf)

                if not has_errors:
                    video.updated_at = datetime.utcnow()
                    db.session.commit()
                    flash(trans("flash_training_updated"), "success")
                    return redirect(url_for(".admin_training_video_list"))
        return render_template(
            "admin_training_video_edit.html",
            video=video,
            playlists=playlists,
            selected_playlist_id=selected_playlist_id,
        )

    @bp.route("/training-videos/<int:video_id>/delete", methods=["POST"], endpoint="admin_training_video_delete")
    @roles_required("admin")
    def admin_training_video_delete(video_id):
        trans = t
        ensure_training_playlist_schema()
        video = TrainingVideo.query.get_or_404(video_id)
        _delete_training_pdf(video)
        db.session.delete(video)
        db.session.commit()
        normalize_training_video_order()
        flash(trans("flash_training_deleted"), "info")
        return redirect(url_for(".admin_training_video_list"))

    @bp.route("/training-videos/<int:video_id>/move-up", methods=["POST"], endpoint="admin_training_video_move_up")
    @roles_required("admin")
    def admin_training_video_move_up(video_id):
        swap_training_video(video_id, "up")
        return redirect(url_for(".admin_training_video_list"))

    @bp.route("/training-videos/<int:video_id>/move-down", methods=["POST"], endpoint="admin_training_video_move_down")
    @roles_required("admin")
    def admin_training_video_move_down(video_id):
        swap_training_video(video_id, "down")
        return redirect(url_for(".admin_training_video_list"))

    # Cost Centers ----------------------------------------------------------

    def _cost_center_orders_with_costs(cost_center_id: int):
        cost_center_orders = (
            Order.query
            .filter_by(cost_center_id=cost_center_id)
            .order_by(Order.created_at.desc(), Order.id.desc())
            .all()
        )
        cost_center_order_costs = {}
        for order in cost_center_orders:
            order_total_cost = 0
            for job in order.print_jobs:
                printer_profile = job.printer_profile
                filament_material = job.filament_material
                machine_hourly_rate = printer_profile.machine_hourly_rate if printer_profile else 0
                maintenance_hourly_rate = printer_profile.maintenance_hourly_rate if printer_profile else 0
                setup_fee = printer_profile.setup_fee if printer_profile else 0
                price_per_g = filament_material.price_per_g if filament_material else 0
                markup_percent = filament_material.markup_percent if filament_material else 0
                drying_fee = filament_material.drying_fee if filament_material else 0
                handling_fee = filament_material.handling_fee if filament_material else 0
                print_hours = (job.duration_min or 0) / 60
                machine_cost = (
                    print_hours * ((machine_hourly_rate or 0) + (maintenance_hourly_rate or 0))
                ) + (setup_fee or 0)
                filament_base_cost = (job.filament_g or 0) * (price_per_g or 0)
                material_cost = (
                    filament_base_cost * (1 + ((markup_percent or 0) / 100))
                ) + (drying_fee or 0) + (handling_fee or 0)
                order_total_cost += machine_cost + material_cost
            cost_center_order_costs[order.id] = order_total_cost
        return cost_center_orders, cost_center_order_costs, sum(cost_center_order_costs.values())

    @bp.route("/cost-centers", endpoint="admin_cost_center_list")
    @roles_required("admin")
    def admin_cost_center_list():
        cost_centers = CostCenter.query.order_by(CostCenter.name.asc()).all()
        order_count_rows = (
            db.session.query(Order.cost_center_id, func.count(Order.id))
            .filter(Order.cost_center_id.isnot(None))
            .group_by(Order.cost_center_id)
            .all()
        )
        order_counts = {cost_center_id: count for cost_center_id, count in order_count_rows}
        return render_template(
            "admin_cost_centers.html",
            cost_centers=cost_centers,
            order_counts=order_counts,
        )

    @bp.route("/cost-centers/new", methods=["GET", "POST"], endpoint="admin_cost_center_new")
    @roles_required("admin")
    def admin_cost_center_new():
        trans = t
        if request.method == "POST":
            name = request.form.get("name", "").strip()
            email = request.form.get("email", "").strip() or None
            note = request.form.get("note", "").strip() or None
            is_active = bool(request.form.get("is_active"))

            if not name:
                flash(trans("flash_cost_center_required"), "danger")
            else:
                existing = CostCenter.query.filter(func.lower(CostCenter.name) == name.lower()).first()
                if existing:
                    flash(trans("flash_cost_center_exists"), "danger")
                else:
                    cc = CostCenter(name=name, email=email, note=note, is_active=is_active)
                    db.session.add(cc)
                    db.session.commit()
                    flash(trans("flash_cost_center_created"), "success")
                    return redirect(url_for(".admin_cost_center_list"))

        return render_template(
            "admin_cost_center_edit.html",
            cost_center=None,
            cost_center_orders=[],
            cost_center_order_costs={},
            cost_center_total_cost=0,
        )

    @bp.route("/cost-centers/<int:cc_id>/edit", methods=["GET", "POST"], endpoint="admin_cost_center_edit")
    @roles_required("admin")
    def admin_cost_center_edit(cc_id):
        trans = t
        cost_center = CostCenter.query.get_or_404(cc_id)

        if request.method == "POST":
            name = request.form.get("name", "").strip()
            email = request.form.get("email", "").strip() or None
            note = request.form.get("note", "").strip() or None
            is_active = bool(request.form.get("is_active"))

            if not name:
                flash(trans("flash_cost_center_required"), "danger")
            else:
                existing = CostCenter.query.filter(func.lower(CostCenter.name) == name.lower()).first()
                if existing and existing.id != cost_center.id:
                    flash(trans("flash_cost_center_exists"), "danger")
                else:
                    cost_center.name = name
                    cost_center.email = email
                    cost_center.note = note
                    cost_center.is_active = is_active
                    db.session.commit()
                    flash(trans("flash_cost_center_updated"), "success")
                    return redirect(url_for(".admin_cost_center_list"))

        cost_center_orders, cost_center_order_costs, cost_center_total_cost = _cost_center_orders_with_costs(
            cost_center.id
        )
        return render_template(
            "admin_cost_center_edit.html",
            cost_center=cost_center,
            cost_center_orders=cost_center_orders,
            cost_center_order_costs=cost_center_order_costs,
            cost_center_total_cost=cost_center_total_cost,
        )

    @bp.route("/cost-centers/<int:cc_id>/pdf", endpoint="admin_cost_center_pdf")
    @roles_required("admin")
    def admin_cost_center_pdf(cc_id):
        trans = t
        cost_center = CostCenter.query.get_or_404(cc_id)
        orders, order_costs, total_cost = _cost_center_orders_with_costs(cost_center.id)
        status_context = build_status_context(load_app_settings(current_app), trans)
        status_labels = status_context.get("order_status_labels", {})
        generated_at = _fmt_datetime(datetime.utcnow())

        lines = [
            "NeoFab",
            f"Version: {APP_VERSION}",
            f"{trans('admin_cost_center_pdf_export_date')}: {generated_at}",
            "",
            trans("admin_cost_center_form_title_edit"),
            f"{trans('admin_cost_center_label_name')}: {cost_center.name}",
            f"{trans('admin_cost_center_label_email')}: {cost_center.email or ''}",
            f"{trans('admin_cost_center_label_is_active')}: {trans('badge_yes') if cost_center.is_active else trans('badge_no')}",
            f"{trans('admin_cost_center_label_note')}: {cost_center.note or ''}",
            "",
            f"{trans('admin_cost_center_orders_title')}: {len(orders)}",
            f"{trans('admin_cost_center_orders_total_cost')}: {total_cost:.2f} EUR",
            "",
        ]

        if orders:
            table_widths = [6, 29, 24, 15, 12, 16]
            table_headers = [
                trans("table_id"),
                trans("title"),
                trans("owner"),
                trans("table_status"),
                trans("print_jobs_table_total_cost"),
                trans("table_created"),
            ]
            lines.append(_format_pdf_table_row(table_headers, table_widths, {4}))
            lines.append(_format_pdf_table_row(["-" * width for width in table_widths], table_widths))
            for order in orders:
                created_at = _fmt_datetime(order.created_at)
                owner = order.user.email if order.user else ""
                status = status_labels.get(order.status, order.status or "")
                lines.append(
                    _format_pdf_table_row(
                        [
                            f"#{order.id}",
                            order.title or "",
                            owner,
                            status,
                            f"{order_costs.get(order.id, 0):.2f} EUR",
                            created_at,
                        ],
                        table_widths,
                        {4},
                    )
                )
            lines.append(_format_pdf_table_row(["-" * width for width in table_widths], table_widths))
            lines.append(
                _format_pdf_table_row(
                    ["", "", "", trans("admin_cost_center_orders_total_cost"), f"{total_cost:.2f} EUR", ""],
                    table_widths,
                    {4},
                )
            )
        else:
            lines.append(trans("admin_cost_center_orders_none"))

        filename = f"cost_center_{cost_center.id}.pdf"
        return current_app.response_class(
            _build_simple_text_pdf(lines),
            mimetype="application/pdf",
            headers={"Content-Disposition": f"attachment; filename={filename}"},
        )

    @bp.route("/cost-centers/<int:cc_id>/delete", methods=["POST"], endpoint="admin_cost_center_delete")
    @roles_required("admin")
    def admin_cost_center_delete(cc_id):
        trans = t
        cost_center = CostCenter.query.get_or_404(cc_id)
        db.session.delete(cost_center)
        db.session.commit()
        flash(trans("flash_cost_center_deleted"), "info")
        return redirect(url_for(".admin_cost_center_list"))

    @bp.route("/cost-centers/export", endpoint="admin_cost_center_export")
    @roles_required("admin")
    def admin_cost_center_export():
        """Exportiert alle Kostenstellen als JSON mit Versionsinfo."""
        cost_centers = CostCenter.query.order_by(CostCenter.name.asc()).all()
        payload = {
            "version": APP_VERSION,
            "cost_centers": [
                {
                    "name": cc.name,
                    "note": cc.note or "",
                    "email": cc.email or "",
                    "is_active": bool(cc.is_active),
                }
                for cc in cost_centers
            ],
        }
        output = json.dumps(payload, ensure_ascii=False, indent=2)

        return current_app.response_class(
            output,
            mimetype="application/json",
            headers={"Content-Disposition": "attachment; filename=NeoFab_cost_centers.json"},
        )

    @bp.route("/cost-centers/import", methods=["POST"], endpoint="admin_cost_center_import")
    @roles_required("admin")
    def admin_cost_center_import():
        """
        Importiert Kostenstellen aus einer JSON-Datei:
        {
          "version": "...",
          "cost_centers": [{ "name": "...", "note": "...", "email": "...", "is_active": true }, ...]
        }
        Bestehende Einträge werden vorher entfernt.
        """
        trans = t
        file = request.files.get("file")
        if not file or not file.filename:
            flash(trans("flash_json_choose_file"), "warning")
            return redirect(url_for(".admin_cost_center_list"))

        try:
            content = file.read().decode("utf-8-sig")
            data = json.loads(content)
        except Exception:
            flash(trans("flash_invalid_json"), "danger")
            return redirect(url_for(".admin_cost_center_list"))

        rows = data.get("cost_centers", []) if isinstance(data, dict) else []

        # Bestehende Kostenstellen vor Import leeren
        CostCenter.query.delete()

        created = skipped = 0
        for entry in rows:
            name = (entry.get("name") or "").strip() if isinstance(entry, dict) else ""
            note = (entry.get("note") or "").strip() if isinstance(entry, dict) else None
            email = (entry.get("email") or "").strip() if isinstance(entry, dict) else None
            is_active = bool(entry.get("is_active")) if isinstance(entry, dict) else True

            if not name:
                skipped += 1
                continue

            db.session.add(
                CostCenter(
                    name=name,
                    note=note or None,
                    email=email or None,
                    is_active=is_active,
                )
            )
            created += 1

        db.session.commit()
        flash(
            trans("flash_import_result_simple").format(
                created=created, skipped=skipped
            ),
            "success",
        )
        return redirect(url_for(".admin_cost_center_list"))

    return bp
