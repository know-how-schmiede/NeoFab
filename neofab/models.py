from datetime import datetime

from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()


# --- User-Modell -------------------------------------------------------------

class User(UserMixin, db.Model):
    """
    Benutzerkonto mit Login-Daten, Rolle und einigen Profilfeldern.
    """
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(50), nullable=False, default="user")
    language = db.Column(db.String(5), nullable=False, default="en")

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

    # Oeffentlichkeits-/Projektfelder
    public_allow_poster = db.Column(db.Boolean, nullable=False, default=False)
    public_allow_web = db.Column(db.Boolean, nullable=False, default=False)
    public_allow_social = db.Column(db.Boolean, nullable=False, default=False)
    public_display_name = db.Column(db.String(200))

    summary_short = db.Column(db.String(255))
    summary_long = db.Column(db.Text)
    project_purpose = db.Column(db.String(255))
    project_use_case = db.Column(db.String(255))
    learning_points = db.Column(db.Text)
    background_info = db.Column(db.Text)
    project_url = db.Column(db.String(500))

    # Status: "new", "in_progress", "on_hold", "completed", "cancelled"
    status = db.Column(db.String(50), nullable=False, default="new")

    # Material & Farbe (FK)
    material_id = db.Column(db.Integer, db.ForeignKey("materials.id"), nullable=True)
    color_id = db.Column(db.Integer, db.ForeignKey("colors.id"), nullable=True)
    cost_center_id = db.Column(db.Integer, db.ForeignKey("cost_centers.id"), nullable=True)

    # Besitzer (User)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)

    # Timestamps
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Beziehungen
    user = db.relationship("User", back_populates="orders")
    material = db.relationship("Material")
    color = db.relationship("Color")
    cost_center = db.relationship("CostCenter")
    messages = db.relationship("OrderMessage", back_populates="order", lazy=True)
    files = db.relationship("OrderFile", back_populates="order", lazy=True)
    images = db.relationship("OrderImage", back_populates="order", lazy=True)
    tags_entry = db.relationship("OrderTag", back_populates="order", uselist=False)


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
    note = db.Column(db.String(255))       # Bemerkung zum Modell
    quantity = db.Column(db.Integer, nullable=False, default=1)  # benötigte Anzahl
    uploaded_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    # Beziehung zurück zum Order
    order = db.relationship("Order", back_populates="files")


# --- OrderImage ---------------------------------------------------------------


class OrderImage(db.Model):
    __tablename__ = "order_images"

    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey("orders.id"), nullable=False)
    original_name = db.Column(db.String(255), nullable=False)
    stored_name = db.Column(db.String(255), nullable=False)
    filesize = db.Column(db.Integer)
    uploaded_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    note = db.Column(db.String(255))

    order = db.relationship("Order", back_populates="images")


# --- OrderTag -----------------------------------------------------------------


class OrderTag(db.Model):
    __tablename__ = "order_tags"

    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey("orders.id"), nullable=False, unique=True)
    tags = db.Column(db.String(300))

    order = db.relationship("Order", back_populates="tags_entry")


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


# --- Training Videos (Tutorials) ---------------------------------------------


class TrainingVideo(db.Model):
    __tablename__ = "training_videos"

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    youtube_url = db.Column(db.String(500), nullable=False)
    sort_order = db.Column(db.Integer, nullable=False, default=0)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f"<TrainingVideo {self.title}>"


__all__ = [
    "db",
    "User",
    "Order",
    "OrderMessage",
    "OrderReadStatus",
    "OrderFile",
    "OrderImage",
    "OrderTag",
    "Material",
    "Color",
    "CostCenter",
    "TrainingVideo",
]
