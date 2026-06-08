from __future__ import annotations

import os
import smtplib
from datetime import datetime, timedelta
from email.utils import getaddresses
from email.message import EmailMessage
from typing import Mapping
from zoneinfo import ZoneInfo

from flask import url_for
from flask_login import current_user

from config import is_email_action_enabled, load_app_settings
from models import Announcement, Order, User


def _format_app_datetime(value: datetime | None, settings: Mapping[str, object]) -> str:
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
        offset_hours = int(settings.get("time_display_offset_hours", 0) or 0)
    except Exception:
        offset_hours = 0

    if offset_hours:
        value = value + timedelta(hours=offset_hours)

    try:
        return value.strftime("%Y-%m-%d %H:%M")
    except Exception:
        return ""


def _split_email_recipients(raw: str | None) -> list[str]:
    if not raw:
        return []
    normalized = raw.replace(";", ",").replace("\n", ",").replace("\r", ",")
    return [
        email.strip()
        for _, email in getaddresses([normalized])
        if email and "@" in email
    ]


def _add_recipients(recipients: list[str], seen: set[str], candidates: list[str]) -> None:
    for email in candidates:
        email = (email or "").strip()
        if not email:
            continue
        key = email.lower()
        if key in seen:
            continue
        recipients.append(email)
        seen.add(key)


def _collect_order_recipients(
    order: Order,
    include_owner: bool = False,
    include_cost_center: bool = False,
) -> list[str]:
    recipients: list[str] = []
    seen: set[str] = set()

    admin_users = User.query.filter_by(role="admin").all()
    for user in admin_users:
        _add_recipients(recipients, seen, _split_email_recipients(user.email))

    if include_owner and order.user:
        _add_recipients(recipients, seen, _split_email_recipients(order.user.email))

    if include_cost_center and order.cost_center:
        _add_recipients(recipients, seen, _split_email_recipients(order.cost_center.email))

    return recipients


def _collect_active_user_recipients() -> list[str]:
    recipients: list[str] = []
    seen: set[str] = set()
    users = User.query.filter_by(is_active=True, deleted_at=None).all()
    for user in users:
        _add_recipients(recipients, seen, _split_email_recipients(user.email))
    return recipients


def _send_message(settings: Mapping[str, object], msg: EmailMessage) -> None:
    smtp_host = settings.get("smtp_host")
    smtp_port = settings.get("smtp_port")
    smtp_use_tls = bool(settings.get("smtp_use_tls"))
    smtp_use_ssl = bool(settings.get("smtp_use_ssl"))
    smtp_user = settings.get("smtp_user")
    smtp_password = settings.get("smtp_password")
    smtp_from = settings.get("smtp_from_address")

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


def send_admin_order_notification(app, order: Order, status_labels: Mapping[str, str] | None = None) -> bool:
    """
    Send a notification email to all admin users (plus order creator) for a newly created order.
    Never raises; returns True on success, False otherwise.
    """
    try:
        settings = load_app_settings(app, force_reload=True)
        if not is_email_action_enabled(settings, "new_order"):
            app.logger.info("New order notification disabled, skipping email.")
            return False

        smtp_host = settings.get("smtp_host")
        smtp_port = settings.get("smtp_port")
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

        status_labels = status_labels or {}
        status_label = status_labels.get(order.status, order.status)
        created_by = current_user.email if current_user.is_authenticated else ""
        created_at = _format_app_datetime(order.created_at, settings)

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

        _send_message(settings, msg)

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


def send_order_status_change_notification(
    app,
    order: Order,
    old_status: str,
    new_status: str,
    status_labels: Mapping[str, str] | None = None,
) -> bool:
    """
    Notify admins and the order owner about a status change.
    Never raises; returns True on success, False otherwise.
    """
    try:
        settings = load_app_settings(app, force_reload=True)
        if not is_email_action_enabled(settings, "order_status_changed"):
            app.logger.info("Order status notification disabled, skipping email.")
            return False

        smtp_host = settings.get("smtp_host")
        smtp_port = settings.get("smtp_port")
        smtp_from = settings.get("smtp_from_address")

        if not smtp_host or not smtp_port or not smtp_from:
            app.logger.info("SMTP not configured, skipping status notification.")
            return False

        recipients = _collect_order_recipients(
            order,
            include_owner=True,
            include_cost_center=True,
        )
        if not recipients:
            app.logger.info("No recipients found, skipping status notification.")
            return False

        try:
            order_url = url_for("order_detail", order_id=order.id, _external=True)
        except Exception:
            order_url = url_for("order_detail", order_id=order.id)

        status_labels = status_labels or {}
        old_label = status_labels.get(old_status, old_status)
        new_label = status_labels.get(new_status, new_status)
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

        _send_message(settings, msg)

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


def send_announcement_attention_notification(app, announcement: Announcement) -> bool:
    """
    Notify all active users about an announcement with priority "Achtung eMail".
    Never raises; returns True on success, False otherwise.
    """
    try:
        settings = load_app_settings(app, force_reload=True)
        if not is_email_action_enabled(settings, "announcement_attention_email"):
            app.logger.info("Announcement attention notification disabled, skipping email.")
            return False

        smtp_host = settings.get("smtp_host")
        smtp_port = settings.get("smtp_port")
        smtp_from = settings.get("smtp_from_address")

        if not smtp_host or not smtp_port or not smtp_from:
            app.logger.info("SMTP not configured, skipping announcement notification.")
            return False

        recipients = _collect_active_user_recipients()
        if not recipients:
            app.logger.info("No recipients found, skipping announcement notification.")
            return False

        try:
            dashboard_url = url_for("dashboard", _external=True)
        except Exception:
            dashboard_url = url_for("dashboard")

        created_by = current_user.email if current_user.is_authenticated else ""

        msg = EmailMessage()
        msg["Subject"] = f"NeoFab: Achtung eMail - {announcement.title}"
        msg["From"] = smtp_from
        msg["To"] = smtp_from
        msg["Bcc"] = ", ".join(recipients)
        if created_by:
            msg["Reply-To"] = created_by

        body_lines = [
            "Eine neue NeoFab-Mitteilung mit der Prioritaet 'Achtung eMail' wurde erstellt.",
            f"Titel: {announcement.title}",
            f"Erstellt von: {created_by}",
            f"Link: {dashboard_url}",
            "",
            "Mitteilung:",
            announcement.body,
        ]
        msg.set_content("\n".join(body_lines))

        _send_message(settings, msg)

        app.logger.info(
            "Sent announcement attention notification for announcement %s to %s",
            announcement.id,
            ", ".join(recipients),
        )
        return True
    except Exception:
        app.logger.exception(
            "Failed to send announcement notification for announcement %s",
            getattr(announcement, "id", "?"),
        )
        return False
