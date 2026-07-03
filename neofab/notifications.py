from __future__ import annotations

import smtplib
from collections.abc import Mapping
from datetime import datetime
from email.utils import getaddresses
from email.message import EmailMessage

from flask import url_for
from flask_login import current_user

from audit_logs import write_audit_log
from config import is_email_action_enabled, load_app_settings
from i18n_utils import DEFAULT_LANG, SUPPORTED_LANGS
from models import Announcement, Order, User
from time_utils import format_app_datetime


class _SafeFormatDict(dict):
    def __missing__(self, key: str) -> str:
        return "{" + key + "}"


def _format_app_datetime(value: datetime | None, settings: Mapping[str, object]) -> str:
    return format_app_datetime(value, settings)


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


def _normalize_language(lang: str | None) -> str:
    value = (lang or DEFAULT_LANG).strip().lower()
    for code in SUPPORTED_LANGS:
        if value.startswith(code):
            return code
    return DEFAULT_LANG


def _collect_order_recipients(
    order: Order,
    include_owner: bool = False,
    include_cost_center: bool = False,
    respect_status_email_enabled: bool = False,
) -> tuple[list[str], dict[str, str]]:
    recipients: list[str] = []
    seen: set[str] = set()
    recipient_languages: dict[str, str] = {}

    admin_users = User.query.filter_by(role="admin").all()
    for user in admin_users:
        if respect_status_email_enabled and not getattr(user, "status_email_enabled", True):
            continue
        user_language = _normalize_language(getattr(user, "language", None))
        for email in _split_email_recipients(user.email):
            key = email.lower()
            if key in seen:
                continue
            seen.add(key)
            recipients.append(email)
            recipient_languages[key] = user_language

    if include_owner and order.user:
        if respect_status_email_enabled and not getattr(order.user, "status_email_enabled", True):
            owner_can_receive_status_email = False
        else:
            owner_can_receive_status_email = True
    else:
        owner_can_receive_status_email = False

    if include_owner and order.user and owner_can_receive_status_email:
        owner_language = _normalize_language(getattr(order.user, "language", None))
        for email in _split_email_recipients(order.user.email):
            key = email.lower()
            if key in seen:
                continue
            seen.add(key)
            recipients.append(email)
            recipient_languages[key] = owner_language

    if include_cost_center and order.cost_center:
        for email in _split_email_recipients(order.cost_center.email):
            key = email.lower()
            if key in seen:
                continue
            seen.add(key)
            recipients.append(email)
            recipient_languages[key] = DEFAULT_LANG

    return recipients, recipient_languages


def _collect_active_user_recipients() -> tuple[list[str], dict[str, str]]:
    recipients: list[str] = []
    seen: set[str] = set()
    recipient_languages: dict[str, str] = {}
    users = User.query.filter_by(is_active=True, deleted_at=None).all()
    for user in users:
        user_language = _normalize_language(getattr(user, "language", None))
        for email in _split_email_recipients(user.email):
            key = email.lower()
            if key in seen:
                continue
            seen.add(key)
            recipients.append(email)
            recipient_languages[key] = user_language
    return recipients, recipient_languages


def _collect_user_welcome_recipients(new_user: User) -> tuple[list[str], dict[str, str]]:
    recipients: list[str] = []
    seen: set[str] = set()
    recipient_languages: dict[str, str] = {}

    user_language = _normalize_language(getattr(new_user, "language", None))
    for email in _split_email_recipients(new_user.email):
        key = email.lower()
        if key not in seen:
            seen.add(key)
            recipients.append(email)
            recipient_languages[key] = user_language

    admin_users = User.query.filter_by(role="admin").all()
    for user in admin_users:
        for email in _split_email_recipients(user.email):
            key = email.lower()
            if key in seen:
                continue
            seen.add(key)
            recipients.append(email)
            recipient_languages[key] = user_language

    return recipients, recipient_languages


def _group_recipients_by_language(
    recipients: list[str],
    recipient_languages: Mapping[str, str],
) -> dict[str, list[str]]:
    grouped: dict[str, list[str]] = {}
    for email in recipients:
        language = _normalize_language(recipient_languages.get(email.lower(), DEFAULT_LANG))
        grouped.setdefault(language, []).append(email)
    return grouped


def _notification_footer(settings: Mapping[str, object], entry_url: str, language: str) -> list[str]:
    generated_at = _format_app_datetime(datetime.utcnow(), settings)
    if language == "de":
        return [
            "",
            "---",
            "NeoFab Systeminformationen",
            f"Erstellt am: {generated_at}",
            f"Einstiegspunkt: {entry_url}",
            "Diese E-Mail wurde automatisch von NeoFab erzeugt.",
            "Bei Rueckfragen nutze bitte den zugehoerigen Auftrags-Chat oder kontaktiere das Werkstatt-Team.",
        ]
    if language == "fr":
        return [
            "",
            "---",
            "Informations systeme NeoFab",
            f"Genere le: {generated_at}",
            f"Point d'entree: {entry_url}",
            "Cet e-mail a ete genere automatiquement par NeoFab.",
            "Pour toute question, utilisez le chat de la commande ou contactez l'equipe de l'atelier.",
        ]
    return [
        "",
        "---",
        "NeoFab System Information",
        f"Generated at: {generated_at}",
        f"Entry point: {entry_url}",
        "This email was generated automatically by NeoFab.",
        "For questions, use the related order chat or contact the workshop team.",
    ]


def _user_display_name(user: User) -> str:
    name = " ".join(
        part.strip()
        for part in (getattr(user, "first_name", "") or "", getattr(user, "last_name", "") or "")
        if part and part.strip()
    )
    return name or getattr(user, "email", "") or "NeoFab User"


def _default_welcome_email_body(language: str) -> str:
    if language == "de":
        return "\n".join(
            [
                "Hallo {display_name},",
                "",
                "herzlich willkommen bei NeoFab. Dein Benutzerkonto wurde erstellt und du kannst NeoFab ab sofort fuer deine Auftraege nutzen.",
                "",
                "In deinem Benutzerprofil kannst du jederzeit die Sprache anpassen und das Design von Hell auf Dunkel umstellen.",
                "",
                "Kurzanleitung:",
                "1. Auftrag erstellen.",
                "2. Auftrags-Art auswaehlen, zum Beispiel Bauteile 3D drucken oder Plakat ausplotten.",
                "3. Zum Auftrag koennen mehrere Bauteile oder mehrere Plakate hochgeladen werden.",
                "",
                "Was NeoFab fuer dich bereitstellt:",
                "- Interner STL-3D-Viewer fuer hochgeladene Modelle.",
                "- Chat-Moeglichkeit fuer Rueckfragen direkt am Auftrag.",
                "- Aktuelle Informationen zum Projekt-Status.",
                "- Zentrale Datenhaltung fuer die Projektbearbeitung, damit keine zusaetzlichen E-Mails mehr noetig sind.",
                "",
                "Profil oeffnen: {profile_url}",
                "Dashboard oeffnen: {dashboard_url}",
            ]
        )
    if language == "fr":
        return "\n".join(
            [
                "Bonjour {display_name},",
                "",
                "bienvenue dans NeoFab. Votre compte utilisateur a ete cree et vous pouvez desormais utiliser NeoFab pour vos commandes.",
                "",
                "Dans votre profil utilisateur, vous pouvez modifier la langue et passer le design du mode clair au mode sombre.",
                "",
                "Guide rapide:",
                "1. Creer une commande.",
                "2. Selectionner le type de commande, par exemple impression 3D de pieces ou trace de poster.",
                "3. Une commande peut contenir plusieurs pieces ou plusieurs posters.",
                "",
                "NeoFab vous propose:",
                "- Visionneuse STL 3D integree pour les modeles televerses.",
                "- Chat pour les questions directement dans la commande.",
                "- Informations actuelles sur le statut du projet.",
                "- Stockage central des donnees de projet, sans e-mails supplementaires.",
                "",
                "Ouvrir le profil: {profile_url}",
                "Ouvrir le tableau de bord: {dashboard_url}",
            ]
        )
    return "\n".join(
        [
            "Hello {display_name},",
            "",
            "welcome to NeoFab. Your user account has been created and you can now use NeoFab for your orders.",
            "",
            "In your user profile, you can change the language and switch the design from light to dark mode at any time.",
            "",
            "Quick guide:",
            "1. Create an order.",
            "2. Select the order type, for example 3D print parts or plot a poster.",
            "3. An order can contain multiple parts or multiple posters.",
            "",
            "NeoFab provides:",
            "- Built-in STL 3D viewer for uploaded models.",
            "- Chat for questions directly on the order.",
            "- Current information about project status.",
            "- Central project data storage, so additional emails are no longer needed.",
            "",
            "Open profile: {profile_url}",
            "Open dashboard: {dashboard_url}",
        ]
    )


def _welcome_email_body(settings: Mapping[str, object], new_user: User, language: str, profile_url: str, dashboard_url: str) -> str:
    custom_texts = settings.get("welcome_email_texts", {})
    if not isinstance(custom_texts, Mapping):
        custom_texts = {}
    template = str(custom_texts.get(language, "") or "").strip() or _default_welcome_email_body(language)
    values = _SafeFormatDict(
        display_name=_user_display_name(new_user),
        first_name=getattr(new_user, "first_name", "") or "",
        last_name=getattr(new_user, "last_name", "") or "",
        email=getattr(new_user, "email", "") or "",
        profile_url=profile_url,
        dashboard_url=dashboard_url,
    )
    return template.format_map(values)


def send_user_activation_notification(
    app,
    user: User,
    activation_url: str,
    expires_at: datetime,
    source: str = "user_activation",
) -> bool:
    """Send a one-time account activation link to a newly created user."""
    try:
        settings = load_app_settings(app, force_reload=True)
        smtp_host = settings.get("smtp_host")
        smtp_port = settings.get("smtp_port")
        smtp_from = settings.get("smtp_from_address")

        if not smtp_host or not smtp_port or not smtp_from:
            app.logger.info("SMTP not configured, skipping user activation notification.")
            return False

        language = _normalize_language(getattr(user, "language", None))
        display_name = _user_display_name(user)
        expires_text = _format_app_datetime(expires_at, settings)
        msg = EmailMessage()
        if language == "de":
            msg["Subject"] = f"NeoFab: Benutzerkonto aktivieren, {display_name}"
            body_lines = [
                f"Hallo {display_name},",
                "",
                "dein NeoFab-Benutzerkonto wurde erstellt.",
                "Bitte aktiviere dein Konto ueber den folgenden Link:",
                activation_url,
                "",
                f"Der Link ist gueltig bis: {expires_text}",
                "",
                "Wenn du dieses Konto nicht angefordert hast, ignoriere diese E-Mail.",
            ]
        elif language == "fr":
            msg["Subject"] = f"NeoFab : activer le compte, {display_name}"
            body_lines = [
                f"Bonjour {display_name},",
                "",
                "votre compte utilisateur NeoFab a ete cree.",
                "Veuillez activer votre compte avec le lien suivant :",
                activation_url,
                "",
                f"Le lien est valable jusqu'a : {expires_text}",
                "",
                "Si vous n'avez pas demande ce compte, ignorez cet e-mail.",
            ]
        else:
            msg["Subject"] = f"NeoFab: Activate account, {display_name}"
            body_lines = [
                f"Hello {display_name},",
                "",
                "your NeoFab user account has been created.",
                "Please activate your account using the following link:",
                activation_url,
                "",
                f"The link is valid until: {expires_text}",
                "",
                "If you did not request this account, ignore this email.",
            ]

        msg["From"] = smtp_from
        msg["To"] = user.email
        created_by = current_user.email if current_user.is_authenticated else ""
        if created_by:
            msg["Reply-To"] = created_by
        body_lines.extend(_notification_footer(settings, activation_url, language))
        msg.set_content("\n".join(body_lines))
        _send_message(settings, msg)
        write_audit_log(
            app,
            "email_sent",
            user=current_user if current_user.is_authenticated else user,
            details={
                "kind": "user_activation",
                "language": language,
                "target_user_id": user.id,
                "target_email": user.email,
                "source": source,
                "subject": msg["Subject"],
                "expires_at": expires_at.isoformat() if expires_at else "",
            },
        )
        return True
    except Exception:
        app.logger.exception(
            "Failed to send user activation notification for user %s",
            getattr(user, "id", "?"),
        )
        return False


def send_password_reset_notification(
    app,
    user: User,
    reset_url: str,
    expires_at: datetime,
) -> bool:
    """Send a one-time password reset link to an active user."""
    try:
        settings = load_app_settings(app, force_reload=True)
        smtp_host = settings.get("smtp_host")
        smtp_port = settings.get("smtp_port")
        smtp_from = settings.get("smtp_from_address")

        if not smtp_host or not smtp_port or not smtp_from:
            app.logger.info("SMTP not configured, skipping password reset notification.")
            return False

        language = _normalize_language(getattr(user, "language", None))
        display_name = _user_display_name(user)
        expires_text = _format_app_datetime(expires_at, settings)
        msg = EmailMessage()
        if language == "de":
            msg["Subject"] = f"NeoFab: Passwort zuruecksetzen, {display_name}"
            body_lines = [
                f"Hallo {display_name},",
                "",
                "fuer dein NeoFab-Benutzerkonto wurde ein Passwort-Reset angefordert.",
                "Bitte setze dein Passwort ueber den folgenden Link neu:",
                reset_url,
                "",
                f"Der Link ist gueltig bis: {expires_text}",
                "",
                "Wenn du diesen Reset nicht angefordert hast, ignoriere diese E-Mail.",
            ]
        elif language == "fr":
            msg["Subject"] = f"NeoFab : reinitialiser le mot de passe, {display_name}"
            body_lines = [
                f"Bonjour {display_name},",
                "",
                "une reinitialisation du mot de passe a ete demandee pour votre compte NeoFab.",
                "Veuillez definir un nouveau mot de passe avec le lien suivant :",
                reset_url,
                "",
                f"Le lien est valable jusqu'a : {expires_text}",
                "",
                "Si vous n'avez pas demande cette reinitialisation, ignorez cet e-mail.",
            ]
        else:
            msg["Subject"] = f"NeoFab: Reset password, {display_name}"
            body_lines = [
                f"Hello {display_name},",
                "",
                "a password reset was requested for your NeoFab user account.",
                "Please set a new password using the following link:",
                reset_url,
                "",
                f"The link is valid until: {expires_text}",
                "",
                "If you did not request this reset, ignore this email.",
            ]

        msg["From"] = smtp_from
        msg["To"] = user.email
        body_lines.extend(_notification_footer(settings, reset_url, language))
        msg.set_content("\n".join(body_lines))
        _send_message(settings, msg)
        write_audit_log(
            app,
            "email_sent",
            user=user,
            details={
                "kind": "password_reset",
                "language": language,
                "target_user_id": user.id,
                "target_email": user.email,
                "subject": msg["Subject"],
                "expires_at": expires_at.isoformat() if expires_at else "",
            },
        )
        return True
    except Exception:
        app.logger.exception(
            "Failed to send password reset notification for user %s",
            getattr(user, "id", "?"),
        )
        return False


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


def send_user_welcome_notification(app, new_user: User, source: str = "user_created") -> bool:
    """Notify the new user and admins that a user account has been created."""
    try:
        settings = load_app_settings(app, force_reload=True)
        if not is_email_action_enabled(settings, "user_welcome"):
            app.logger.info("User welcome notification disabled, skipping email.")
            return False

        smtp_host = settings.get("smtp_host")
        smtp_port = settings.get("smtp_port")
        smtp_from = settings.get("smtp_from_address")

        if not smtp_host or not smtp_port or not smtp_from:
            app.logger.info("SMTP not configured, skipping user welcome notification.")
            return False

        recipients, recipient_languages = _collect_user_welcome_recipients(new_user)
        if not recipients:
            app.logger.info("No recipients found, skipping user welcome notification.")
            return False
        recipients_by_language = _group_recipients_by_language(recipients, recipient_languages)

        try:
            profile_url = url_for("profile", _external=True)
        except Exception:
            profile_url = url_for("profile")
        try:
            dashboard_url = url_for("dashboard", _external=True)
        except Exception:
            dashboard_url = url_for("dashboard")

        created_by = current_user.email if current_user.is_authenticated else ""
        for language, lang_recipients in recipients_by_language.items():
            msg = EmailMessage()
            if language == "de":
                msg["Subject"] = f"NeoFab: Willkommen, {_user_display_name(new_user)}"
            elif language == "fr":
                msg["Subject"] = f"NeoFab : Bienvenue, {_user_display_name(new_user)}"
            else:
                msg["Subject"] = f"NeoFab: Welcome, {_user_display_name(new_user)}"
            msg["From"] = smtp_from
            msg["To"] = ", ".join(lang_recipients)
            if created_by:
                msg["Reply-To"] = created_by

            body_lines = [
                _welcome_email_body(settings, new_user, language, profile_url, dashboard_url),
                "",
            ]
            if language == "de":
                body_lines.extend(
                    [
                        "Kontodetails:",
                        f"- E-Mail: {new_user.email}",
                        f"- Rolle: {new_user.role}",
                        f"- Sprache: {_normalize_language(getattr(new_user, 'language', None))}",
                    ]
                )
                if created_by:
                    body_lines.append(f"- Erstellt von: {created_by}")
            elif language == "fr":
                body_lines.extend(
                    [
                        "Details du compte:",
                        f"- E-mail: {new_user.email}",
                        f"- Role: {new_user.role}",
                        f"- Langue: {_normalize_language(getattr(new_user, 'language', None))}",
                    ]
                )
                if created_by:
                    body_lines.append(f"- Cree par: {created_by}")
            else:
                body_lines.extend(
                    [
                        "Account details:",
                        f"- Email: {new_user.email}",
                        f"- Role: {new_user.role}",
                        f"- Language: {_normalize_language(getattr(new_user, 'language', None))}",
                    ]
                )
                if created_by:
                    body_lines.append(f"- Created by: {created_by}")

            body_lines.extend(_notification_footer(settings, dashboard_url, language))
            msg.set_content("\n".join(body_lines))

            _send_message(settings, msg)
            write_audit_log(
                app,
                "email_sent",
                user=current_user if current_user.is_authenticated else new_user,
                details={
                    "kind": "user_welcome",
                    "language": language,
                    "target_user_id": new_user.id,
                    "target_email": new_user.email,
                    "source": source,
                    "subject": msg["Subject"],
                    "recipient_count": len(lang_recipients),
                    "recipients": lang_recipients,
                },
            )

        app.logger.info("Sent user welcome notification for user %s", new_user.id)
        return True
    except Exception:
        app.logger.exception(
            "Failed to send user welcome notification for user %s",
            getattr(new_user, "id", "?"),
        )
        return False


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

        recipients, recipient_languages = _collect_order_recipients(order, include_owner=True)
        if not recipients:
            app.logger.info("No recipients found, skipping admin notification.")
            return False
        recipients_by_language = _group_recipients_by_language(recipients, recipient_languages)

        try:
            order_url = url_for("order_detail", order_id=order.id, _external=True)
        except Exception:
            order_url = url_for("order_detail", order_id=order.id)

        status_labels = status_labels or {}
        status_label = status_labels.get(order.status, order.status)
        created_by = current_user.email if current_user.is_authenticated else ""
        created_at = _format_app_datetime(order.created_at, settings)

        category_name = order.category.name if order.category else "3D Print"
        area_name = order.area.name if order.area else "-"
        for language, lang_recipients in recipients_by_language.items():
            msg = EmailMessage()
            if language == "de":
                msg["Subject"] = f"NeoFab: Neuer Auftrag #{order.id}"
            elif language == "fr":
                msg["Subject"] = f"NeoFab : Nouvelle commande #{order.id}"
            else:
                msg["Subject"] = f"NeoFab: New order #{order.id}"
            msg["From"] = smtp_from
            msg["To"] = ", ".join(lang_recipients)
            if order.user and order.user.email:
                msg["Reply-To"] = order.user.email

            if language == "de":
                body_lines = [
                    "Hallo,",
                    "",
                    "ein neuer NeoFab-Auftrag wurde erstellt und erfordert Aufmerksamkeit.",
                    "",
                    "Auftragsdetails:",
                    f"- ID: {order.id}",
                    f"- Titel: {order.title}",
                    f"- Kategorie: {category_name}",
                    f"- Bereich: {area_name}",
                    f"- Status: {status_label}",
                    f"- Erstellt von: {created_by}",
                    f"- Erstellt am: {created_at}",
                    "",
                    f"Auftrag oeffnen: {order_url}",
                ]
                if order.summary_short:
                    body_lines.extend(["", "Kurzbeschreibung:", order.summary_short])
            elif language == "fr":
                body_lines = [
                    "Bonjour,",
                    "",
                    "une nouvelle commande NeoFab a ete creee et requiert votre attention.",
                    "",
                    "Details de la commande:",
                    f"- ID: {order.id}",
                    f"- Titre: {order.title}",
                    f"- Categorie: {category_name}",
                    f"- Domaine: {area_name}",
                    f"- Statut: {status_label}",
                    f"- Creee par: {created_by}",
                    f"- Creee le: {created_at}",
                    "",
                    f"Ouvrir la commande: {order_url}",
                ]
                if order.summary_short:
                    body_lines.extend(["", "Resume:", order.summary_short])
            else:
                body_lines = [
                    "Hello,",
                    "",
                    "a new NeoFab order has been created and requires attention.",
                    "",
                    "Order details:",
                    f"- ID: {order.id}",
                    f"- Title: {order.title}",
                    f"- Category: {category_name}",
                    f"- Area: {area_name}",
                    f"- Status: {status_label}",
                    f"- Created by: {created_by}",
                    f"- Created at: {created_at}",
                    "",
                    f"Open order: {order_url}",
                ]
                if order.summary_short:
                    body_lines.extend(["", "Summary:", order.summary_short])

            body_lines.extend(_notification_footer(settings, order_url, language))
            msg.set_content("\n".join(body_lines))

            _send_message(settings, msg)
            write_audit_log(
                app,
                "email_sent",
                user=current_user,
                details={
                    "kind": "new_order",
                    "language": language,
                    "order_id": order.id,
                    "subject": msg["Subject"],
                    "recipient_count": len(lang_recipients),
                    "recipients": lang_recipients,
                },
            )

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
    action_key: str = "order_status_changed",
    procurement_articles: list[object] | None = None,
    procurement_all_ordered: bool = False,
) -> bool:
    """
    Notify admins and the order owner about a status change.
    Never raises; returns True on success, False otherwise.
    """
    try:
        settings = load_app_settings(app, force_reload=True)
        if not is_email_action_enabled(settings, action_key):
            app.logger.info("Order status notification disabled, skipping email.")
            return False

        smtp_host = settings.get("smtp_host")
        smtp_port = settings.get("smtp_port")
        smtp_from = settings.get("smtp_from_address")

        if not smtp_host or not smtp_port or not smtp_from:
            app.logger.info("SMTP not configured, skipping status notification.")
            return False

        recipients, recipient_languages = _collect_order_recipients(
            order,
            include_owner=True,
            include_cost_center=True,
            respect_status_email_enabled=True,
        )
        if not recipients:
            app.logger.info("No recipients found, skipping status notification.")
            return False
        recipients_by_language = _group_recipients_by_language(recipients, recipient_languages)

        try:
            order_url = url_for("order_detail", order_id=order.id, _external=True)
        except Exception:
            order_url = url_for("order_detail", order_id=order.id)

        status_labels = status_labels or {}
        old_label = status_labels.get(old_status, old_status)
        new_label = status_labels.get(new_status, new_status)
        changed_by = current_user.email if current_user.is_authenticated else ""

        category_name = order.category.name if order.category else "3D Print"
        area_name = order.area.name if order.area else "-"
        for language, lang_recipients in recipients_by_language.items():
            msg = EmailMessage()
            if procurement_all_ordered:
                if language == "de":
                    msg["Subject"] = f"NeoFab: Alle Artikel fuer Auftrag #{order.id} sind bestellt"
                elif language == "fr":
                    msg["Subject"] = f"NeoFab : Tous les articles de la commande #{order.id} sont commandes"
                else:
                    msg["Subject"] = f"NeoFab: All articles for order #{order.id} are ordered"
            elif new_status == "in_progress":
                if language == "de":
                    msg["Subject"] = f"NeoFab: Auftrag #{order.id} ist jetzt in Bearbeitung"
                elif language == "fr":
                    msg["Subject"] = f"NeoFab : Commande #{order.id} en cours"
                else:
                    msg["Subject"] = f"NeoFab: Order #{order.id} is now in progress"
            elif new_status == "completed":
                if language == "de":
                    msg["Subject"] = f"NeoFab: Auftrag #{order.id} ist jetzt Abgeschlossen"
                elif language == "fr":
                    msg["Subject"] = f"NeoFab : Commande #{order.id} terminee"
                else:
                    msg["Subject"] = f"NeoFab: Order #{order.id} is now completed"
            else:
                if language == "de":
                    msg["Subject"] = f"NeoFab: Auftrag #{order.id} Status geaendert zu {new_label}"
                elif language == "fr":
                    msg["Subject"] = f"NeoFab : Commande #{order.id} statut modifie vers {new_label}"
                else:
                    msg["Subject"] = f"NeoFab: Order #{order.id} status changed to {new_label}"
            msg["From"] = smtp_from
            msg["To"] = ", ".join(lang_recipients)
            if order.user and order.user.email:
                msg["Reply-To"] = order.user.email

            if language == "de":
                if procurement_all_ordered:
                    intro = "Alle Artikel dieses Beschaffungsauftrags sind bestellt."
                elif new_status == "in_progress":
                    intro = "Der Auftrag wurde auf In Bearbeitung gesetzt."
                elif new_status == "completed":
                    intro = "Der Auftrag wurde auf Abgeschlossen gesetzt."
                else:
                    intro = "Der Status eines NeoFab-Auftrags wurde geaendert."
                body_lines = [
                    "Hallo,",
                    "",
                    intro,
                    "",
                    "Auftragsdetails:",
                    f"- ID: {order.id}",
                    f"- Titel: {order.title}",
                    f"- Kategorie: {category_name}",
                    f"- Bereich: {area_name}",
                    f"- Status: {old_label} -> {new_label}",
                    f"- Geaendert von: {changed_by}",
                    "",
                    f"Auftrag oeffnen: {order_url}",
                ]
                if order.summary_short:
                    body_lines.extend(["", "Kurzbeschreibung:", order.summary_short])
            elif language == "fr":
                if procurement_all_ordered:
                    intro = "Tous les articles de cette commande d'achat sont commandes."
                elif new_status == "in_progress":
                    intro = "La commande a ete passee en cours."
                elif new_status == "completed":
                    intro = "La commande a ete passee en terminee."
                else:
                    intro = "Le statut d'une commande NeoFab a ete modifie."
                body_lines = [
                    "Bonjour,",
                    "",
                    intro,
                    "",
                    "Details de la commande:",
                    f"- ID: {order.id}",
                    f"- Titre: {order.title}",
                    f"- Categorie: {category_name}",
                    f"- Domaine: {area_name}",
                    f"- Statut: {old_label} -> {new_label}",
                    f"- Modifie par: {changed_by}",
                    "",
                    f"Ouvrir la commande: {order_url}",
                ]
                if order.summary_short:
                    body_lines.extend(["", "Resume:", order.summary_short])
            else:
                if procurement_all_ordered:
                    intro = "All articles for this procurement order are ordered."
                elif new_status == "in_progress":
                    intro = "The order is now in progress."
                elif new_status == "completed":
                    intro = "The order is now completed."
                else:
                    intro = "The status of a NeoFab order has changed."
                body_lines = [
                    "Hello,",
                    "",
                    intro,
                    "",
                    "Order details:",
                    f"- ID: {order.id}",
                    f"- Title: {order.title}",
                    f"- Category: {category_name}",
                    f"- Area: {area_name}",
                    f"- Status: {old_label} -> {new_label}",
                    f"- Changed by: {changed_by}",
                    "",
                    f"Open order: {order_url}",
                ]
                if order.summary_short:
                    body_lines.extend(["", "Summary:", order.summary_short])

            if procurement_articles:
                if language == "de":
                    body_lines.extend(["", "Bestellte Artikel:"])
                    quantity_label = "Menge"
                    price_label = "Preis"
                elif language == "fr":
                    body_lines.extend(["", "Articles commandes:"])
                    quantity_label = "Quantite"
                    price_label = "Prix"
                else:
                    body_lines.extend(["", "Ordered articles:"])
                    quantity_label = "Quantity"
                    price_label = "Price"
                for article in procurement_articles:
                    article_name = getattr(article, "article_name", "") or f"#{getattr(article, 'id', '')}"
                    quantity = getattr(article, "quantity", None) or 1
                    price = getattr(article, "price_per_unit_incl_vat", None)
                    price_text = f"{price:.2f} EUR" if price is not None else "-"
                    body_lines.append(
                        f"- {article_name} | {quantity_label}: {quantity} | {price_label}: {price_text}"
                    )

            body_lines.extend(_notification_footer(settings, order_url, language))
            msg.set_content("\n".join(body_lines))

            _send_message(settings, msg)
            write_audit_log(
                app,
                "email_sent",
                user=current_user,
                details={
                    "kind": action_key,
                    "language": language,
                    "order_id": order.id,
                    "old_status": old_status,
                    "new_status": new_status,
                    "subject": msg["Subject"],
                    "recipient_count": len(lang_recipients),
                    "recipients": lang_recipients,
                },
            )

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


def send_poster_printed_notification(
    app,
    order: Order,
    poster,
) -> bool:
    """Notify admins and the order owner that a poster has been marked printed."""
    try:
        settings = load_app_settings(app, force_reload=True)
        if not is_email_action_enabled(settings, "poster_printed"):
            app.logger.info("Poster printed notification disabled, skipping email.")
            return False

        smtp_host = settings.get("smtp_host")
        smtp_port = settings.get("smtp_port")
        smtp_from = settings.get("smtp_from_address")

        if not smtp_host or not smtp_port or not smtp_from:
            app.logger.info("SMTP not configured, skipping poster notification.")
            return False

        recipients, recipient_languages = _collect_order_recipients(
            order,
            include_owner=True,
            include_cost_center=True,
            respect_status_email_enabled=True,
        )
        if not recipients:
            app.logger.info("No recipients found, skipping poster notification.")
            return False
        recipients_by_language = _group_recipients_by_language(recipients, recipient_languages)

        try:
            order_url = url_for("order_detail", order_id=order.id, _external=True)
        except Exception:
            order_url = url_for("order_detail", order_id=order.id)

        poster_name = poster.original_name or poster.stored_name or f"#{poster.id}"
        category_name = order.category.name if order.category else "Plotter"
        area_name = order.area.name if order.area else "-"
        created_by = current_user.email if current_user.is_authenticated else ""

        for language, lang_recipients in recipients_by_language.items():
            msg = EmailMessage()
            if language == "de":
                msg["Subject"] = f"NeoFab: Plakat gedruckt bei Auftrag #{order.id}"
                intro = "Ein Plakat wurde als gedruckt markiert."
                body_lines = [
                    "Hallo,",
                    "",
                    intro,
                    "",
                    "Auftragsdetails:",
                    f"- ID: {order.id}",
                    f"- Titel: {order.title}",
                    f"- Kategorie: {category_name}",
                    f"- Bereich: {area_name}",
                    f"- Plakat: {poster_name}",
                    f"- Markiert von: {created_by}",
                    "",
                    f"Auftrag oeffnen: {order_url}",
                ]
            elif language == "fr":
                msg["Subject"] = f"NeoFab : Affiche imprimee pour la commande #{order.id}"
                intro = "Une affiche a ete marquee comme imprimee."
                body_lines = [
                    "Bonjour,",
                    "",
                    intro,
                    "",
                    "Details de la commande:",
                    f"- ID: {order.id}",
                    f"- Titre: {order.title}",
                    f"- Categorie: {category_name}",
                    f"- Domaine: {area_name}",
                    f"- Affiche: {poster_name}",
                    f"- Marquee par: {created_by}",
                    "",
                    f"Ouvrir la commande: {order_url}",
                ]
            else:
                msg["Subject"] = f"NeoFab: Poster printed for order #{order.id}"
                intro = "A poster has been marked as printed."
                body_lines = [
                    "Hello,",
                    "",
                    intro,
                    "",
                    "Order details:",
                    f"- ID: {order.id}",
                    f"- Title: {order.title}",
                    f"- Category: {category_name}",
                    f"- Area: {area_name}",
                    f"- Poster: {poster_name}",
                    f"- Marked by: {created_by}",
                    "",
                    f"Open order: {order_url}",
                ]

            msg["From"] = smtp_from
            msg["To"] = ", ".join(lang_recipients)
            if order.user and order.user.email:
                msg["Reply-To"] = order.user.email

            body_lines.extend(_notification_footer(settings, order_url, language))
            msg.set_content("\n".join(body_lines))

            _send_message(settings, msg)
            write_audit_log(
                app,
                "email_sent",
                user=current_user,
                details={
                    "kind": "poster_printed",
                    "language": language,
                    "order_id": order.id,
                    "poster_id": getattr(poster, "id", None),
                    "subject": msg["Subject"],
                    "recipient_count": len(lang_recipients),
                    "recipients": lang_recipients,
                },
            )

        app.logger.info(
            "Sent poster printed notification for order %s to %s",
            order.id,
            ", ".join(recipients),
        )
        return True
    except Exception:
        app.logger.exception(
            "Failed to send poster printed notification for order %s",
            getattr(order, "id", "?"),
        )
        return False


def send_procurement_article_list_email(
    app,
    order: Order,
    recipient_raw: str,
    articles: list,
    position_count: int,
    total_price: float,
) -> bool:
    """Send a procurement article list snapshot to arbitrary recipients."""
    try:
        settings = load_app_settings(app, force_reload=True)
        smtp_host = settings.get("smtp_host")
        smtp_port = settings.get("smtp_port")
        smtp_from = settings.get("smtp_from_address")

        if not smtp_host or not smtp_port or not smtp_from:
            app.logger.info("SMTP not configured, skipping procurement article list email.")
            return False

        recipients = _split_email_recipients(recipient_raw)
        if not recipients:
            app.logger.info("No valid recipients found, skipping procurement article list email.")
            return False

        try:
            order_url = url_for("order_detail", order_id=order.id, tab="articles", _external=True)
        except Exception:
            order_url = url_for("order_detail", order_id=order.id, tab="articles")

        snapshot_at = _format_app_datetime(datetime.utcnow(), settings)
        sent_by = current_user.email if current_user.is_authenticated else ""
        msg = EmailMessage()
        msg["Subject"] = f"NeoFab: Artikelliste Auftrag #{order.id}"
        msg["From"] = smtp_from
        msg["To"] = ", ".join(recipients)
        if sent_by:
            msg["Reply-To"] = sent_by

        body_lines = [
            "Hallo,",
            "",
            "anbei die aktuelle Artikelliste aus NeoFab.",
            "",
            "Auftrag:",
            f"- ID: {order.id}",
            f"- Titel: {order.title}",
            f"- Zeitpunkt: {snapshot_at}",
            f"- Versendet von: {sent_by or '-'}",
            "",
            "Artikelliste:",
        ]

        if articles:
            for article in articles:
                position_number = getattr(article, "position_number", None) or getattr(article, "id", "")
                quantity = getattr(article, "quantity", None) or 1
                price = getattr(article, "price_per_unit_incl_vat", None)
                total = (price or 0.0) * quantity
                supplier = getattr(article, "supplier", None) or "-"
                status = getattr(article, "status", None) or "-"
                price_text = f"{price:.2f} EUR" if price is not None else "-"
                total_text = f"{total:.2f} EUR" if price is not None else "-"
                body_lines.append(
                    f"#{position_number} {getattr(article, 'article_name', '')}"
                    f" | Lieferant: {supplier}"
                    f" | Anzahl: {quantity}"
                    f" | Status: {status}"
                    f" | Preis pro Stueck: {price_text}"
                    f" | Gesamt: {total_text}"
                )
                description = (getattr(article, "article_description", None) or "").strip()
                if description:
                    body_lines.append(f"  Beschreibung: {description}")
                article_url = (getattr(article, "article_url", None) or "").strip()
                if article_url:
                    body_lines.append(f"  Link: {article_url}")
        else:
            body_lines.append("- Keine Artikel vorhanden.")

        body_lines.extend(
            [
                "",
                "Statistik:",
                f"- Artikel-Positionen: {position_count}",
                f"- Gesamtpreis: {total_price:.2f} EUR",
                "",
                f"Auftrag oeffnen: {order_url}",
            ]
        )
        body_lines.extend(_notification_footer(settings, order_url, "de"))
        msg.set_content("\n".join(body_lines))

        _send_message(settings, msg)
        write_audit_log(
            app,
            "email_sent",
            user=current_user if current_user.is_authenticated else None,
            details={
                "kind": "procurement_article_list",
                "order_id": order.id,
                "subject": msg["Subject"],
                "recipient_count": len(recipients),
                "recipients": recipients,
                "position_count": position_count,
                "total_price": total_price,
                "snapshot_at": snapshot_at,
            },
        )
        app.logger.info(
            "Sent procurement article list for order %s to %s",
            order.id,
            ", ".join(recipients),
        )
        return True
    except Exception:
        app.logger.exception(
            "Failed to send procurement article list for order %s",
            getattr(order, "id", "?"),
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

        recipients, recipient_languages = _collect_active_user_recipients()
        if not recipients:
            app.logger.info("No recipients found, skipping announcement notification.")
            return False
        recipients_by_language = _group_recipients_by_language(recipients, recipient_languages)

        try:
            dashboard_url = url_for("dashboard", _external=True)
        except Exception:
            dashboard_url = url_for("dashboard")

        created_by = current_user.email if current_user.is_authenticated else ""

        for language, lang_recipients in recipients_by_language.items():
            msg = EmailMessage()
            if language == "de":
                msg["Subject"] = f"NeoFab: Achtung eMail - {announcement.title}"
            elif language == "fr":
                msg["Subject"] = f"NeoFab : Message important - {announcement.title}"
            else:
                msg["Subject"] = f"NeoFab: Attention email - {announcement.title}"
            msg["From"] = smtp_from
            msg["To"] = smtp_from
            msg["Bcc"] = ", ".join(lang_recipients)
            if created_by:
                msg["Reply-To"] = created_by

            if language == "de":
                body_lines = [
                    "Hallo,",
                    "",
                    "eine neue NeoFab-Mitteilung mit der Prioritaet 'Achtung eMail' wurde erstellt.",
                    "",
                    "Mitteilungsdetails:",
                    f"- Titel: {announcement.title}",
                    f"- Erstellt von: {created_by}",
                    "",
                    "Mitteilung:",
                    announcement.body,
                    "",
                    f"Zum Dashboard: {dashboard_url}",
                ]
            elif language == "fr":
                body_lines = [
                    "Bonjour,",
                    "",
                    "une nouvelle annonce NeoFab avec la priorite e-mail importante a ete creee.",
                    "",
                    "Details de l'annonce:",
                    f"- Titre: {announcement.title}",
                    f"- Creee par: {created_by}",
                    "",
                    "Annonce:",
                    announcement.body,
                    "",
                    f"Vers le tableau de bord: {dashboard_url}",
                ]
            else:
                body_lines = [
                    "Hello,",
                    "",
                    "a new NeoFab announcement with priority Attention email has been created.",
                    "",
                    "Announcement details:",
                    f"- Title: {announcement.title}",
                    f"- Created by: {created_by}",
                    "",
                    "Announcement:",
                    announcement.body,
                    "",
                    f"Go to dashboard: {dashboard_url}",
                ]

            body_lines.extend(_notification_footer(settings, dashboard_url, language))
            msg.set_content("\n".join(body_lines))

            _send_message(settings, msg)
            write_audit_log(
                app,
                "email_sent",
                user=current_user,
                details={
                    "kind": "announcement_attention_email",
                    "language": language,
                    "announcement_id": announcement.id,
                    "subject": msg["Subject"],
                    "recipient_count": len(lang_recipients),
                    "recipients": lang_recipients,
                },
            )

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
