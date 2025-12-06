# ============================================================
# NeoFab – einfache 3D-Druck-Auftragsverwaltung
# ============================================================
# - User-Registrierung & Login
# - Aufträge mit Material / Farbe
# - Chat-ähnliche Kommunikation pro Auftrag
# - Upload mehrerer 3D-Dateien (STL / 3MF) pro Auftrag
# - Download & Löschen von Dateien
# - Dashboard mit Files-Zähler pro Auftrag
# ============================================================

from version import APP_VERSION
from datetime import datetime
from pathlib import Path
import os
import logging
import json

from sqlalchemy import func

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

from flask_sqlalchemy import SQLAlchemy

from flask_login import (
    LoginManager,
    UserMixin,
    login_user,
    login_required,
    logout_user,
    current_user,
)

from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

from functools import wraps


# ============================================================
# Grundkonfiguration & Logging
# ============================================================

app = Flask(__name__)

# Basis-Verzeichnis (Root des Projekts)
BASE_DIR = Path(__file__).resolve().parent

# Upload-Ordner für 3D-Modelle, z.B. "uploads/models"
UPLOAD_FOLDER = BASE_DIR / "uploads" / "models"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config["UPLOAD_FOLDER"] = str(UPLOAD_FOLDER)

# Maximal erlaubte Upload-Größe (z.B. 50 MB)
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

# Abwärtskompatibilität für alte deutsche Statuswerte
STATUS_LABELS.setdefault("neu", "New")
STATUS_LABELS.setdefault("in_bearbeitung", "In progress")
STATUS_LABELS.setdefault("abgeschlossen", "Completed")

# Secret Key & Datenbank-Config
app.config["SECRET_KEY"] = os.environ.get("NEOFAB_SECRET_KEY", "dev-secret-change-me")

# SQLite-DB im Projektverzeichnis (absoluter Pfad)
db_path = BASE_DIR / "neofab.db"
app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{db_path}"

app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False


# ============================================================
# Globale Template-Variablen
# ============================================================

@app.context_processor
def inject_globals():
    """
    Stellt globale Werte in allen Templates zur Verfügung.
    """
    return {
        "app_version": APP_VERSION,
        "status_labels": STATUS_LABELS,
    }


# ============================================================
# DB-Initialisierung & Hilfsfunktionen
# ============================================================

db = SQLAlchemy(app)


@app.template_filter("nl2br")
def nl2br_filter(s: str):
    """
    Filter für Jinja: wandelt Zeilenumbrüche in <br> um und escaped den Text zuvor.
    Eignet sich für Chat-/Text-Ausgabe.
    """
    if not s:
        return ""
    return Markup("<br>".join(escape(s).splitlines()))


# ============================================================
# Login- / Rollen-Setup
# ============================================================

login_manager = LoginManager(app)
login_manager.login_view = "login"  # wohin bei @login_required ohne Login?


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
                abort(403)  # Forbidden
            return view_func(*args, **kwargs)

        return wrapped

    return decorator


# ============================================================
# Datenbank-Modelle
# ============================================================

# --- User-Modell -------------------------------------------------------------

class User(UserMixin, db.Model):
    """
    Benutzerkonto mit Login-Daten, Rolle und einigen Profilfeldern.
    """
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(50), nullable=False, default="user")

    # Zusatzfelder
    salutation = db.Column(db.String(50))   # Anrede
    first_name = db.Column(db.String(100))  # Vorname
    last_name = db.Column(db.String(100))   # Nachname
    address = db.Column(db.String(255))     # Adresse
    position = db.Column(db.String(100))    # Position / Funktion
    cost_center = db.Column(db.String(100)) # Kostenstelle
    study_program = db.Column(db.String(150))  # Studiengang
    note = db.Column(db.Text)              # Freitext / Bemerkung

    # Timestamps
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    last_login_at = db.Column(db.DateTime, nullable=True)

    # Beziehung zu Aufträgen
    orders = db.relationship("Order", back_populates="user", lazy=True)

    def set_password(self, password: str):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)


# --- Order-Modell ------------------------------------------------------------

class Order(db.Model):
    """
    Auftragskopf: Titel, Beschreibung, Status, Owner,
    optional Material/Farbe, Nachrichten & Dateien.
    """
    __tablename__ = "orders"

    id = db.Column(db.Integer, primary_key=True)

    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=True)

    # Status: "new", "in_progress", "on_hold", "completed", "cancelled"
    status = db.Column(db.String(50), nullable=False, default="new")

    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(
        db.DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    # Besitzer / Anforderer
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    user = db.relationship("User", back_populates="orders")

    # Material- und Farb-Auswahl (optional)
    material_id = db.Column(db.Integer, db.ForeignKey("materials.id"), nullable=True)
    color_id = db.Column(db.Integer, db.ForeignKey("colors.id"), nullable=True)
    cost_center_id = db.Column(db.Integer, db.ForeignKey("cost_centers.id"), nullable=True)

    material = db.relationship("Material")
    color = db.relationship("Color")
    cost_center = db.relationship("CostCenter")

    # Nachrichten zum Auftrag
    messages = db.relationship(
        "OrderMessage",
        back_populates="order",
        cascade="all, delete-orphan",
        order_by="OrderMessage.created_at",
    )

    # Hochgeladene 3D-Modelle (STL / 3MF) zu diesem Auftrag
    files = db.relationship(
        "OrderFile",
        back_populates="order",
        cascade="all, delete-orphan",
        lazy=True,
    )


# --- OrderMessage (Chat-/Kommunikationseintrag) ------------------------------

class OrderMessage(db.Model):
    __tablename__ = "order_messages"

    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    order_id = db.Column(db.Integer, db.ForeignKey("orders.id"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)

    order = db.relationship("Order", back_populates="messages")
    user = db.relationship("User")


# --- OrderReadStatus (wann hat welcher User den Auftrag zuletzt gelesen) -----

class OrderReadStatus(db.Model):
    __tablename__ = "order_read_status"

    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey("orders.id"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    last_read_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    order = db.relationship("Order")
    user = db.relationship("User")

    __table_args__ = (
        db.UniqueConstraint("order_id", "user_id", name="uq_order_user"),
    )


# --- OrderFile (hochgeladene 3D-Modelle) ------------------------------------

class OrderFile(db.Model):
    """
    Einzelner Datei-Eintrag zu einem Auftrag (z.B. STL oder 3MF).
    """
    __tablename__ = "order_files"

    id = db.Column(db.Integer, primary_key=True)

    # Zugehöriger Auftrag
    order_id = db.Column(db.Integer, db.ForeignKey("orders.id"), nullable=False)

    # Dateinamen
    original_name = db.Column(db.String(255), nullable=False)  # vom User hochgeladen
    stored_name = db.Column(db.String(255), nullable=False)    # technischer Name auf Platte (mit ID-Präfix)

    # Metadaten
    file_type = db.Column(db.String(20))   # z.B. 'stl' oder '3mf'
    filesize = db.Column(db.Integer)       # in Bytes
    uploaded_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    # Beziehung zurück zum Order
    order = db.relationship("Order", back_populates="files")


# --- Stammdaten: Material ----------------------------------------------------

class Material(db.Model):
    __tablename__ = "materials"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)
    description = db.Column(db.String(255))  # Kurzbeschreibung / Notizen

    def __repr__(self):
        return f"<Material {self.name}>"


# --- Stammdaten: Color -------------------------------------------------------

class Color(db.Model):
    __tablename__ = "colors"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)
    hex_code = db.Column(db.String(7))  # z.B. '#FF0000'

    def __repr__(self):
        return f"<Color {self.name}>"


# --- Stammdaten: Cost Center -------------------------------------------------


class CostCenter(db.Model):
    __tablename__ = "cost_centers"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    note = db.Column(db.Text)
    email = db.Column(db.String(255))
    is_active = db.Column(db.Boolean, nullable=False, default=True)

    def __repr__(self):
        return f"<CostCenter {self.name}>"


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
    """Initialisiert die Datenbank (einmalig ausführen)."""
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
        ("Weiß", "#FFFFFF"),
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
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        user = User.query.filter_by(email=email).first()
        if user and user.check_password(password):
            login_user(user)
            user.last_login_at = datetime.utcnow()
            db.session.commit()

            flash("Login successful.", "success")
            next_page = request.args.get("next")
            return redirect(next_page or url_for("dashboard"))
        else:
            flash("Invalid email or password.", "danger")

    return render_template("login.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    """Registrierungs-Formular & Account-Anlage für neue Nutzer."""
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        password2 = request.form.get("password2", "")

        # einfache Validierung
        if not email or not password:
            flash("Please fill in all required fields.", "danger")
        elif password != password2:
            flash("Passwords do not match.", "danger")
        elif User.query.filter_by(email=email).first():
            flash("This email is already registered.", "warning")
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
            flash("Registration successful. You can now log in.", "success")
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

        # Basisvalidierungen
        if not email:
            flash("Email is required.", "danger")
        else:
            existing = User.query.filter_by(email=email).first()
            if existing and existing.id != user.id:
                flash("Another account with this email already exists.", "danger")
            elif new_password and new_password != new_password2:
                flash("Passwords do not match.", "danger")
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

                if new_password:
                    user.set_password(new_password)

                db.session.commit()
                flash("Profile updated.", "success")
                return redirect(url_for("profile"))

    return render_template("profile.html", user=user)


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
    # Stammdaten laden (für GET und POST)
    materials = Material.query.order_by(Material.name.asc()).all()
    colors = Color.query.order_by(Color.name.asc()).all()
    cost_centers = CostCenter.query.order_by(CostCenter.name.asc()).all()

    if request.method == "POST":
        title = request.form.get("title", "").strip()
        description = request.form.get("description", "").strip()

        # --- Status-Handling ---
        if current_user.role == "admin":
            # Admin darf initialen Status wählen
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

        if not title:
            flash("Please provide a title for the order.", "danger")
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
                flash("Only STL and 3MF files are allowed.", "warning")
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

        flash("Order has been created.", "success")
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
    - Status ändern (nur Admin)
    - Nachrichten schreiben
    - Dateien hochladen / löschen
    """
    order = Order.query.get_or_404(order_id)

    # Access control: normale User sehen nur eigene Aufträge
    if current_user.role != "admin" and order.user_id != current_user.id:
        abort(403)

    if request.method == "POST":
        app.logger.debug(f"[order_detail] POST data for order {order.id}: {dict(request.form)}")

        action = request.form.get("action")

        # --- 1) Auftragsdaten aktualisieren --------------------------------
        if action == "update_order":
            title = request.form.get("title", "").strip()
            description = request.form.get("description", "").strip()
            status = request.form.get("status", order.status)

            app.logger.debug(
                f"[order_detail] UPDATE_ORDER before: id={order.id}, "
                f"title={order.title!r}, status={order.status!r}"
            )
            app.logger.debug(f"[order_detail] Form status value: {status!r}")

            if not title:
                flash("Title must not be empty.", "danger")
            else:
                order.title = title
                order.description = description or None

                # Material / Farbe / Kostenstelle aktualisieren (für alle Rollen erlaubt)
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

                # Statuswechsel nur für Admin
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
                flash("Order has been updated.", "success")
                return redirect(url_for("order_detail", order_id=order.id))

        # --- 2) Neue Nachricht hinzufügen ----------------------------------
        elif action == "add_message":
            content = request.form.get("content", "").strip()
            app.logger.debug(f"[order_detail] ADD_MESSAGE for order {order.id}: {content!r}")

            if not content:
                flash("Please enter a message.", "danger")
            else:
                msg = OrderMessage(
                    order_id=order.id,
                    user_id=current_user.id,
                    content=content,
                )
                db.session.add(msg)
                db.session.commit()
                app.logger.debug(f"[order_detail] Message {msg.id} added to order {order.id}")
                flash("Message has been added.", "success")
                return redirect(url_for("order_detail", order_id=order.id))

        # --- 3) Auftrag stornieren -----------------------------------------
        elif action == "cancel_order":
            app.logger.debug(
                f"[order_detail] CANCEL_ORDER requested by user={current_user.email}, "
                f"order_id={order.id}, current_status={order.status!r}"
            )
            # User darf nur eigene Aufträge stornieren, Admin alle
            if current_user.role == "admin" or order.user_id == current_user.id:
                if order.status not in ("completed", "cancelled"):
                    order.status = "cancelled"
                    db.session.commit()
                    app.logger.debug(
                        f"[order_detail] Order {order.id} cancelled. New status={order.status!r}"
                    )
                    flash("Order has been cancelled.", "info")
                else:
                    app.logger.debug(
                        f"[order_detail] Order {order.id} cannot be cancelled (status={order.status!r})"
                    )
                    flash("This order cannot be cancelled anymore.", "warning")
            else:
                app.logger.debug(
                    f"[order_detail] CANCEL_ORDER forbidden for user={current_user.email}, "
                    f"order_id={order.id}"
                )

            return redirect(url_for("order_detail", order_id=order.id))

        # --- 4) Zusätzliche Datei hochladen --------------------------------
        elif action == "upload_file":
            file = request.files.get("model_file")
            if not file or not file.filename:
                flash("Please select a file to upload.", "warning")
                return redirect(url_for("order_detail", order_id=order.id))

            original_name = file.filename
            safe_name = secure_filename(original_name)

            _, ext = os.path.splitext(safe_name)
            ext = ext.lower().lstrip(".")  # "stl" oder "3mf"

            allowed_ext = {"stl", "3mf"}
            if ext not in allowed_ext:
                flash("Only STL and 3MF files are allowed.", "warning")
                return redirect(url_for("order_detail", order_id=order.id))

            # OrderFile-Eintrag mit Platzhalter
            order_file = OrderFile(
                order_id=order.id,
                original_name=original_name,
                stored_name="",
                file_type=ext,
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

            flash("File has been uploaded.", "success")
            return redirect(url_for("order_detail", order_id=order.id))

        # --- 5) Datei löschen ----------------------------------------------
        elif action == "delete_file":
            try:
                file_id = int(request.form.get("file_id", "0"))
            except ValueError:
                file_id = 0

            if not file_id:
                flash("Invalid file ID.", "danger")
                return redirect(url_for("order_detail", order_id=order.id))

            order_file = OrderFile.query.filter_by(
                id=file_id,
                order_id=order.id
            ).first()

            if not order_file:
                flash("File not found.", "warning")
                return redirect(url_for("order_detail", order_id=order.id))

            # Physische Datei löschen
            order_folder = Path(app.config["UPLOAD_FOLDER"]) / f"order_{order.id}"
            full_path = order_folder / order_file.stored_name

            if full_path.exists():
                try:
                    full_path.unlink()
                except OSError:
                    app.logger.warning(
                        f"[order_detail] Could not delete file on disk: {full_path}"
                    )

            # DB-Eintrag löschen
            db.session.delete(order_file)
            db.session.commit()

            app.logger.debug(
                f"[order_detail] Deleted file {file_id} for order {order.id}"
            )

            flash("File has been deleted.", "info")
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

    # Zusätzlich in Session merken (pro User, pro Order)
    session_key = f"order_last_read_{order.id}"
    session[session_key] = now.isoformat()
    app.logger.debug(
        f"[order_detail] Session last_read set for order={order.id}, key={session_key}, value={session[session_key]}"
    )

    messages = order.messages

    # Stammdaten für Auswahlfelder laden
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
    )


@app.route("/orders/<int:order_id>/messages-fragment")
@login_required
def order_messages_fragment(order_id):
    """
    Liefert nur den Nachrichten-Thread als HTML-Fragment fǬr Auto-Refresh.
    """
    order = Order.query.get_or_404(order_id)

    # Access control wie in order_detail
    if current_user.role != "admin" and order.user_id != current_user.id:
        abort(403)

    messages = order.messages
    return render_template("order_messages_fragment.html", messages=messages)


# ============================================================
# Datei-Download
# ============================================================

@app.route("/orders/<int:order_id>/files/<int:file_id>/download")
@login_required
def download_order_file(order_id, file_id):
    """
    Einfache Download-Route für eine Datei zu einem Auftrag.
    """
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
        flash("File not found on server.", "danger")
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
    Übersicht aller Aufträge (Admin: alle, User: nur eigene).
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

    # 5) "last_new_message" pro Order berechnen (für "new message"-Badge)
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
# Admin-Bereich: User, Material, Farben
# ============================================================

@app.route("/admin")
@roles_required("admin")
def admin_panel():
    """Einfache Admin-Startseite."""
    return render_template("admin.html")


@app.route("/admin/users")
@roles_required("admin")
def admin_user_list():
    """Übersicht aller User (nur für Admin)."""
    users = User.query.order_by(User.id.asc()).all()
    return render_template("admin_users.html", users=users)


@app.route("/admin/users/<int:user_id>/edit", methods=["GET", "POST"])
@roles_required("admin")
def admin_user_edit(user_id):
    """User-Daten bearbeiten (Admin)."""
    user = User.query.get_or_404(user_id)

    if request.method == "POST":
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
            flash("Email is required.", "danger")
        else:
            existing = User.query.filter_by(email=email).first()
            if existing and existing.id != user.id:
                flash("Another user with this email already exists.", "danger")
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
                flash("User updated.", "success")
                return redirect(url_for("admin_user_list"))

    return render_template("admin_user_edit.html", user=user)


# --- Admin: Material-Stammdaten ---------------------------------------------

@app.route("/admin/materials")
@roles_required("admin")
def admin_material_list():
    materials = Material.query.order_by(Material.name.asc()).all()
    return render_template("admin_materials.html", materials=materials)


@app.route("/admin/materials/export")
@roles_required("admin")
def admin_material_export():
    """
    Exportiert alle Materialien als JSON (name, description) mit Versionsinfo.
    """
    materials = Material.query.order_by(Material.name.asc()).all()
    payload = {
        "version": APP_VERSION,
        "materials": [
            {"name": m.name, "description": m.description or ""}
            for m in materials
        ],
    }
    output = json.dumps(payload, ensure_ascii=False, indent=2)

    return app.response_class(
        output,
        mimetype="application/json",
        headers={"Content-Disposition": "attachment; filename=NeoFab_materials.json"},
    )


@app.route("/admin/materials/import", methods=["POST"])
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
    file = request.files.get("file")
    if not file or not file.filename:
        flash("Please choose a JSON file to import.", "warning")
        return redirect(url_for("admin_material_list"))

    try:
        content = file.read().decode("utf-8-sig")
        data = json.loads(content)
    except Exception:
        flash("Could not read file. Please upload a valid JSON export.", "danger")
        return redirect(url_for("admin_material_list"))

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
    flash(f"Import finished: {created} created, {skipped} skipped.", "success")
    return redirect(url_for("admin_material_list"))


@app.route("/admin/materials/new", methods=["GET", "POST"])
@roles_required("admin")
def admin_material_new():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        description = request.form.get("description", "").strip() or None

        if not name:
            flash("Material name is required.", "danger")
        else:
            existing = Material.query.filter_by(name=name).first()
            if existing:
                flash("A material with this name already exists.", "danger")
            else:
                m = Material(name=name, description=description)
                db.session.add(m)
                db.session.commit()
                flash("Material created.", "success")
                return redirect(url_for("admin_material_list"))

    return render_template("admin_material_edit.html", material=None)


@app.route("/admin/materials/<int:material_id>/edit", methods=["GET", "POST"])
@roles_required("admin")
def admin_material_edit(material_id):
    material = Material.query.get_or_404(material_id)

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        description = request.form.get("description", "").strip() or None

        if not name:
            flash("Material name is required.", "danger")
        else:
            existing = Material.query.filter_by(name=name).first()
            if existing and existing.id != material.id:
                flash("Another material with this name already exists.", "danger")
            else:
                material.name = name
                material.description = description
                db.session.commit()
                flash("Material updated.", "success")
                return redirect(url_for("admin_material_list"))

    return render_template("admin_material_edit.html", material=material)


@app.route("/admin/materials/<int:material_id>/delete", methods=["POST"])
@roles_required("admin")
def admin_material_delete(material_id):
    material = Material.query.get_or_404(material_id)
    db.session.delete(material)
    db.session.commit()
    flash("Material deleted.", "info")
    return redirect(url_for("admin_material_list"))


# --- Admin: Color-Stammdaten -----------------------------------------------

@app.route("/admin/colors")
@roles_required("admin")
def admin_color_list():
    colors = Color.query.order_by(Color.name.asc()).all()
    return render_template("admin_colors.html", colors=colors)


@app.route("/admin/colors/export")
@roles_required("admin")
def admin_color_export():
    """
    Exportiert alle Farben als JSON (name, hex_code) mit Versionsinfo.
    """
    colors = Color.query.order_by(Color.name.asc()).all()
    payload = {
        "version": APP_VERSION,
        "colors": [
            {"name": c.name, "hex_code": c.hex_code or ""}
            for c in colors
        ],
    }
    output = json.dumps(payload, ensure_ascii=False, indent=2)

    return app.response_class(
        output,
        mimetype="application/json",
        headers={"Content-Disposition": "attachment; filename=NeoFab_colors.json"},
    )


@app.route("/admin/colors/import", methods=["POST"])
@roles_required("admin")
def admin_color_import():
    """
    Importiert Farben aus einer JSON-Datei:
    {
      "version": "...",
      "colors": [{ "name": "...", "hex_code": "#RRGGBB" }, ...]
    }
    Existierende Namen werden aktualisiert, neue angelegt.
    """
    file = request.files.get("file")
    if not file or not file.filename:
        flash("Please choose a JSON file to import.", "warning")
        return redirect(url_for("admin_color_list"))

    try:
        content = file.read().decode("utf-8-sig")
        data = json.loads(content)
    except Exception:
        flash("Could not read file. Please upload a valid JSON export.", "danger")
        return redirect(url_for("admin_color_list"))

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
    flash(f"Import finished: {created} created, {updated} updated, {skipped} skipped.", "success")
    return redirect(url_for("admin_color_list"))


@app.route("/admin/colors/new", methods=["GET", "POST"])
@roles_required("admin")
def admin_color_new():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        hex_code = request.form.get("hex_code", "").strip() or None

        if not name:
            flash("Color name is required.", "danger")
        else:
            existing = Color.query.filter_by(name=name).first()
            if existing:
                flash("A color with this name already exists.", "danger")
            else:
                c = Color(name=name, hex_code=hex_code)
                db.session.add(c)
                db.session.commit()
                flash("Color created.", "success")
                return redirect(url_for("admin_color_list"))

    return render_template("admin_color_edit.html", color=None)


@app.route("/admin/colors/<int:color_id>/edit", methods=["GET", "POST"])
@roles_required("admin")
def admin_color_edit(color_id):
    color = Color.query.get_or_404(color_id)

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        hex_code = request.form.get("hex_code", "").strip() or None

        if not name:
            flash("Color name is required.", "danger")
        else:
            existing = Color.query.filter_by(name=name).first()
            if existing and existing.id != color.id:
                flash("Another color with this name already exists.", "danger")
            else:
                color.name = name
                color.hex_code = hex_code
                db.session.commit()
                flash("Color updated.", "success")
                return redirect(url_for("admin_color_list"))

    return render_template("admin_color_edit.html", color=color)


@app.route("/admin/colors/<int:color_id>/delete", methods=["POST"])
@roles_required("admin")
def admin_color_delete(color_id):
    color = Color.query.get_or_404(color_id)
    db.session.delete(color)
    db.session.commit()
    flash("Color deleted.", "info")
    return redirect(url_for("admin_color_list"))


# --- Admin: Cost Center -------------------------------------------------------


@app.route("/admin/cost-centers")
@roles_required("admin")
def admin_cost_center_list():
    cost_centers = CostCenter.query.order_by(CostCenter.name.asc()).all()
    return render_template("admin_cost_centers.html", cost_centers=cost_centers)


@app.route("/admin/cost-centers/new", methods=["GET", "POST"])
@roles_required("admin")
def admin_cost_center_new():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip() or None
        note = request.form.get("note", "").strip() or None
        is_active = bool(request.form.get("is_active"))

        if not name:
            flash("Name is required.", "danger")
        else:
            existing = CostCenter.query.filter(func.lower(CostCenter.name) == name.lower()).first()
            if existing:
                flash("A cost center with this name already exists.", "danger")
            else:
                cc = CostCenter(name=name, email=email, note=note, is_active=is_active)
                db.session.add(cc)
                db.session.commit()
                flash("Cost center created.", "success")
                return redirect(url_for("admin_cost_center_list"))

    return render_template("admin_cost_center_edit.html", cost_center=None)


@app.route("/admin/cost-centers/<int:cc_id>/edit", methods=["GET", "POST"])
@roles_required("admin")
def admin_cost_center_edit(cc_id):
    cost_center = CostCenter.query.get_or_404(cc_id)

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip() or None
        note = request.form.get("note", "").strip() or None
        is_active = bool(request.form.get("is_active"))

        if not name:
            flash("Name is required.", "danger")
        else:
            existing = CostCenter.query.filter(func.lower(CostCenter.name) == name.lower()).first()
            if existing and existing.id != cost_center.id:
                flash("Another cost center with this name already exists.", "danger")
            else:
                cost_center.name = name
                cost_center.email = email
                cost_center.note = note
                cost_center.is_active = is_active
                db.session.commit()
                flash("Cost center updated.", "success")
                return redirect(url_for("admin_cost_center_list"))

    return render_template("admin_cost_center_edit.html", cost_center=cost_center)


@app.route("/admin/cost-centers/<int:cc_id>/delete", methods=["POST"])
@roles_required("admin")
def admin_cost_center_delete(cc_id):
    cost_center = CostCenter.query.get_or_404(cc_id)
    db.session.delete(cost_center)
    db.session.commit()
    flash("Cost center deleted.", "info")
    return redirect(url_for("admin_cost_center_list"))


@app.route("/admin/cost-centers/export")
@roles_required("admin")
def admin_cost_center_export():
    """
    Exportiert alle Kostenstellen als JSON mit Versionsinfo.
    """
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

    return app.response_class(
        output,
        mimetype="application/json",
        headers={"Content-Disposition": "attachment; filename=NeoFab_cost_centers.json"},
    )


@app.route("/admin/cost-centers/import", methods=["POST"])
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
    file = request.files.get("file")
    if not file or not file.filename:
        flash("Please choose a JSON file to import.", "warning")
        return redirect(url_for("admin_cost_center_list"))

    try:
        content = file.read().decode("utf-8-sig")
        data = json.loads(content)
    except Exception:
        flash("Could not read file. Please upload a valid JSON export.", "danger")
        return redirect(url_for("admin_cost_center_list"))

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
    flash(f"Import finished: {created} created, {skipped} skipped.", "success")
    return redirect(url_for("admin_cost_center_list"))


# ============================================================
# Logout
# ============================================================

@app.route("/logout")
@login_required
def logout():
    logout_user()
    flash("You have been logged out.", "info")
    return redirect(url_for("landing"))


# ============================================================
# Dev-Start
# ============================================================

if __name__ == "__main__":
    app.run(debug=True)
