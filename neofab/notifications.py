from __future__ import annotations

import smtplib
from email.message import EmailMessage
from typing import Mapping

from flask import url_for
from flask_login import current_user

from config import load_app_settings
from models import Order, User


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


def send_admin_order_notification(app, order: Order, status_labels: Mapping[str, str] | None = None) -> bool:
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

        status_labels = status_labels or {}
        status_label = status_labels.get(order.status, order.status)
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
