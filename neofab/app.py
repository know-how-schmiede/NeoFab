from version import APP_VERSION
from datetime import datetime
from sqlalchemy import func
import os
import logging


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
# --- Simple logging config ---
logging.basicConfig(level=logging.DEBUG)
app.logger.setLevel(logging.DEBUG)
# ------------------------------

ORDER_STATUSES = [
    ("new", "New"),
    ("in_progress", "In progress"),
    ("on_hold", "On hold"),
    ("completed", "Completed"),
    ("cancelled", "Cancelled"),
]

# Mapping for display
STATUS_LABELS = {value: label for value, label in ORDER_STATUSES}

# Backwards compatibility for old German codes in DB
STATUS_LABELS.setdefault("neu", "New")
STATUS_LABELS.setdefault("in_bearbeitung", "In progress")
STATUS_LABELS.setdefault("abgeschlossen", "Completed")



# === Konfiguration ===
app.config["SECRET_KEY"] = os.environ.get("NEOFAB_SECRET_KEY", "dev-secret-change-me")
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///neofab.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

@app.context_processor
def inject_globals():
    """
    Stellt globale Werte in allen Templates zur Verfügung.
    """
    return {
        "app_version": APP_VERSION,
        "status_labels": STATUS_LABELS,
    }



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

    # Status: internal codes: "new", "in_progress", "on_hold", "completed", "cancelled"
    status = db.Column(db.String(50), nullable=False, default="new")


    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(
        db.DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    user = db.relationship("User", back_populates="orders")

    # NEU: Nachrichten zum Auftrag
    messages = db.relationship(
        "OrderMessage",
        back_populates="order",
        cascade="all, delete-orphan",
        order_by="OrderMessage.created_at",
    )



class OrderMessage(db.Model):
    __tablename__ = "order_messages"

    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    order_id = db.Column(db.Integer, db.ForeignKey("orders.id"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)

    order = db.relationship("Order", back_populates="messages")
    user = db.relationship("User")


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

        # --- Status-Handling ---
        if current_user.role == "admin":
            # Admin may choose initial status
            status = request.form.get("status", "new")
            valid_status_values = [s[0] for s in ORDER_STATUSES]
            if status not in valid_status_values:
                status = "new"
        else:
            # Normal users always start with "new"
            status = "new"
        # ------------------------

        if not title:
            flash("Please provide a title for the order.", "danger")
            return render_template(
                "orders_new.html",
                order_statuses=ORDER_STATUSES,
            )

        order = Order(
            title=title,
            description=description or None,
            status=status,
            user_id=current_user.id,
        )
        db.session.add(order)
        db.session.commit()

        app.logger.debug(
            f"[new_order] Created order id={order.id}, title={order.title!r}, "
            f"status={order.status!r}, user={current_user.email}"
        )

        flash("Order has been created.", "success")
        return redirect(url_for("dashboard"))

    # GET
    return render_template(
        "orders_new.html",
        order_statuses=ORDER_STATUSES,
    )




@app.route("/orders/<int:order_id>", methods=["GET", "POST"])
@login_required
def order_detail(order_id):
    order = Order.query.get_or_404(order_id)

    # Access control
    if current_user.role != "admin" and order.user_id != current_user.id:
        abort(403)

    if request.method == "POST":
        app.logger.debug(f"[order_detail] POST data for order {order.id}: {dict(request.form)}")

        action = request.form.get("action")

        # --- Update order fields ---
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

                # Only admin may change status
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

        # --- Add message ---
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

        # --- Cancel / deactivate order (user or admin) ---
        elif action == "cancel_order":
            app.logger.debug(
                f"[order_detail] CANCEL_ORDER requested by user={current_user.email}, "
                f"order_id={order.id}, current_status={order.status!r}"
            )
            # User may only cancel his own orders, admin may cancel all
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

    # --- Mark as read for current user (GET and after POST redirects) ---
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
    # -----------------------------------------------------

    messages = order.messages
    app.logger.debug(
        f"[order_detail] Render detail for order {order.id}: status={order.status!r}, "
        f"messages_count={len(messages)}"
    )
    return render_template(
        "order_detail.html",
        order=order,
        messages=messages,
        order_statuses=ORDER_STATUSES,
    )




@app.route("/dashboard")
@login_required
def dashboard():
    app.logger.debug(
        f"[dashboard] user={current_user.email}, role={current_user.role}"
    )

    # 1) Load orders, depending on role
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
        )

    order_ids = [o.id for o in orders]
    for o in orders:
        app.logger.debug(
            f"[dashboard] Order id={o.id}, title={o.title!r}, status={o.status!r}"
        )

    # 2) Latest message per order
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

    # 3) Read status for current user
    read_states = (
        db.session.query(
            OrderReadStatus.order_id,
            OrderReadStatus.last_read_at,
        )
        .filter(
            OrderReadStatus.user_id == current_user.id,
            OrderReadStatus.order_id.in_(order_ids),
        )
        .all()
    )
    read_by_order = {order_id: last_read for order_id, last_read in read_states}
    app.logger.debug(f"[dashboard] read_by_order: {read_by_order}")

    # 4) Compute "last new message" per order for this user
    last_new_message = {}
    for o in orders:
        latest = latest_by_order.get(o.id)  # datetime or None
        last_read = read_by_order.get(o.id)  # datetime or None

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
    )







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