from version import APP_VERSION
from datetime import datetime


from flask import Flask, render_template, redirect, url_for, request, flash
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
from functools import wraps
from flask import abort

import os

app = Flask(__name__)

# === Konfiguration ===
app.config["SECRET_KEY"] = os.environ.get("NEOFAB_SECRET_KEY", "dev-secret-change-me")
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///neofab.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

@app.context_processor
def inject_app_version():
    """
    Stellt 'app_version' in allen Templates zur Verfügung.
    """
    return {"app_version": APP_VERSION}


db = SQLAlchemy(app)

login_manager = LoginManager(app)
login_manager.login_view = "login"   # wohin bei @login_required ohne Login?


# === User-Modell ===
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(50), nullable=False, default="user")

    # Zusatzfelder
    salutation = db.Column(db.String(50))        # Anrede
    first_name = db.Column(db.String(100))      # Vorname
    last_name = db.Column(db.String(100))       # Nachname
    address = db.Column(db.String(255))         # Adresse
    position = db.Column(db.String(100))        # Position
    cost_center = db.Column(db.String(100))     # Kostenstelle
    study_program = db.Column(db.String(150))   # Studiengang
    note = db.Column(db.Text)                   # Bemerkung

    # Timestamps
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    last_login_at = db.Column(db.DateTime, nullable=True)

    # Beziehung zu Aufträgen
    orders = db.relationship("Order", back_populates="user", lazy=True)

    def set_password(self, password: str):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)


# === Order-Modell ===
class Order(db.Model):
    __tablename__ = "orders"

    id = db.Column(db.Integer, primary_key=True)

    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=True)

    # Status: z. B. "neu", "in_bearbeitung", "abgeschlossen"
    status = db.Column(db.String(50), nullable=False, default="neu")

    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Zuordnung zum User
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    user = db.relationship("User", back_populates="orders")




@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

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


# === CLI-Helfer zum Initialisieren der DB ===
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

@app.cli.command("version")
def show_version():
    """Zeigt die aktuelle NeoFab-Version an."""
    print(f"NeoFab version: {APP_VERSION}")


# === Routen ===

@app.route("/")
def landing():
    return render_template("landing.html")


@app.route("/login", methods=["GET", "POST"])
def login():
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


@app.route("/orders/new", methods=["GET", "POST"])
@login_required
def new_order():
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        description = request.form.get("description", "").strip()

        if not title:
            flash("Bitte einen Titel für den Auftrag angeben.", "danger")
            return render_template("orders_new.html")

        order = Order(
            title=title,
            description=description or None,
            status="neu",
            user_id=current_user.id,
        )
        db.session.add(order)
        db.session.commit()

        flash("Auftrag wurde erstellt.", "success")
        return redirect(url_for("dashboard"))

    return render_template("orders_new.html")


@app.route("/dashboard")
@login_required
def dashboard():
    # Admin sieht alle neuen Aufträge
    if current_user.role == "admin":
        orders = (
            Order.query
            .filter_by(status="neu")
            .order_by(Order.created_at.desc())
            .all()
        )
    else:
        # Normaler User sieht nur seine eigenen Aufträge
        orders = (
            Order.query
            .filter_by(user_id=current_user.id)
            .order_by(Order.created_at.desc())
            .all()
        )

    return render_template("dashboard.html", orders=orders)


@app.route("/admin")
@roles_required("admin")
def admin_panel():
    return render_template("admin.html")

@app.route("/admin/users")
@roles_required("admin")
def admin_user_list():
    users = User.query.order_by(User.id.asc()).all()
    return render_template("admin_users.html", users=users)


@app.route("/admin/users/<int:user_id>/edit", methods=["GET", "POST"])
@roles_required("admin")
def admin_user_edit(user_id):
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



@app.route("/logout")
@login_required
def logout():
    logout_user()
    flash("You have been logged out.", "info")
    return redirect(url_for("landing"))


if __name__ == "__main__":
    app.run(debug=True)