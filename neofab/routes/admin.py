from __future__ import annotations

import json
from typing import Callable, Optional

from flask import (
    Blueprint,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)
from sqlalchemy import func

from auth_utils import roles_required
from config import SETTINGS_FILE, coerce_positive_int, load_app_settings, save_app_settings
from models import Color, CostCenter, Material, User, db
from version import APP_VERSION


def _translator(get_translator: Callable[[], Optional[Callable[[str], str]]]) -> Callable[[str], str]:
    trans = get_translator()
    return trans or (lambda key: key)


def create_admin_blueprint(get_translator: Callable[[], Optional[Callable[[str], str]]]) -> Blueprint:
    bp = Blueprint("admin", __name__, url_prefix="/admin")

    t = lambda key: _translator(get_translator)(key)

    # Admin Panel / Settings -------------------------------------------------

    @bp.route("/", endpoint="admin_panel")
    @roles_required("admin")
    def admin_panel():
        """Einfache Admin-Startseite."""
        return render_template("admin.html")

    @bp.route("/settings", methods=["GET", "POST"], endpoint="admin_settings")
    @roles_required("admin")
    def admin_settings():
        """Systemweite Einstellungen (Session-Timeout etc.)."""
        trans = t
        settings = load_app_settings(current_app, force_reload=True)

        if request.method == "POST":
            raw_timeout = (request.form.get("session_timeout_minutes") or "").strip()
            timeout_value = coerce_positive_int(raw_timeout, None)

            if timeout_value is None:
                flash(trans("flash_settings_invalid_timeout"), "danger")
            else:
                try:
                    updated_settings = settings.copy()
                    updated_settings["session_timeout_minutes"] = timeout_value
                    save_app_settings(current_app, updated_settings)
                    flash(trans("flash_settings_saved"), "success")
                    return redirect(url_for(".admin_settings"))
                except Exception:
                    current_app.logger.exception("Failed to save admin settings")
                    flash(trans("flash_settings_save_error"), "danger")

        return render_template(
            "admin_settings.html",
            settings=settings,
            settings_path=str(SETTINGS_FILE),
        )

    # User Management -------------------------------------------------------

    @bp.route("/users", endpoint="admin_user_list")
    @roles_required("admin")
    def admin_user_list():
        """Übersicht aller User (nur für Admin)."""
        users = User.query.order_by(User.id.asc()).all()
        return render_template("admin_users.html", users=users)

    @bp.route("/users/<int:user_id>/edit", methods=["GET", "POST"], endpoint="admin_user_edit")
    @roles_required("admin")
    def admin_user_edit(user_id):
        """User-Daten bearbeiten (Admin)."""
        user = User.query.get_or_404(user_id)

        if request.method == "POST":
            trans = t
            email = request.form.get("email", "").strip().lower()
            role = request.form.get("role", "user").strip()
            new_password = request.form.get("password", "")

            salutation = request.form.get("salutation") or None
            first_name = request.form.get("first_name") or None
            last_name = request.form.get("last_name") or None
            address = request.form.get("address") or None
            position = request.form.get("position") or None
            cost_center = request.form.get("cost_center") or None
            study_program = request.form.get("study_program") or None
            note = request.form.get("note") or None

            if not email:
                flash(trans("flash_email_required"), "danger")
            else:
                existing = User.query.filter_by(email=email).first()
                if existing and existing.id != user.id:
                    flash(trans("flash_user_email_exists"), "danger")
                else:
                    user.email = email
                    user.role = role

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

                    db.session.commit()
                    flash(trans("flash_user_updated"), "success")
                    return redirect(url_for(".admin_user_list"))

        return render_template("admin_user_edit.html", user=user)

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

    # Cost Centers ----------------------------------------------------------

    @bp.route("/cost-centers", endpoint="admin_cost_center_list")
    @roles_required("admin")
    def admin_cost_center_list():
        cost_centers = CostCenter.query.order_by(CostCenter.name.asc()).all()
        return render_template("admin_cost_centers.html", cost_centers=cost_centers)

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

        return render_template("admin_cost_center_edit.html", cost_center=None)

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

        return render_template("admin_cost_center_edit.html", cost_center=cost_center)

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
