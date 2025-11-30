from version import APP_VERSION

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
    role = db.Column(db.String(50), nullable=False, default="user")  # <- NEU

    def set_password(self, password: str):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)



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
            user = User(email=email, role="user")  # <- Rolle setzen
            user.set_password(password)
            db.session.add(user)
            db.session.commit()
            flash("Registration successful. You can now log in.", "success")
            return redirect(url_for("login"))

    return render_template("register.html")


@app.route("/dashboard")
@login_required
def dashboard():
    """Platzhalter für spätere Auftragsverwaltung."""
    return render_template("dashboard.html")

@app.route("/admin")
@roles_required("admin")
def admin_panel():
    return render_template("admin.html")


@app.route("/logout")
@login_required
def logout():
    logout_user()
    flash("You have been logged out.", "info")
    return redirect(url_for("landing"))


if __name__ == "__main__":
    app.run(debug=True)