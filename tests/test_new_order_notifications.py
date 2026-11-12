"""New-order delivery, recipient filtering and upgrade regression tests."""
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

from flask import Flask
from flask_login import LoginManager
from sqlalchemy import text

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "neofab"))
from models import db, Order, OrderCategory, OrderFile, OrderPosterFile, OrderProcurementArticle, User, UserOrderCategoryPermission
from notifications import send_admin_order_notification
from schema_utils import ensure_new_order_notification_schema


class NewOrderNotificationTests(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.config.update(SQLALCHEMY_DATABASE_URI="sqlite://", SECRET_KEY="test")
        db.init_app(self.app)
        LoginManager(self.app).user_loader(lambda user_id: None)
        self.app.add_url_rule("/orders/<int:order_id>", endpoint="order_detail", view_func=lambda order_id: "")
        context = self.app.test_request_context("/")
        context.push()
        self.addCleanup(context.pop)
        self.addCleanup(db.engine.dispose)
        self.addCleanup(db.session.remove)
        db.create_all()
        self.category = OrderCategory(key="plotter", name="Plotter")
        self.owner = User(email="owner@example.test", password_hash="unused")
        db.session.add_all([self.category, self.owner])
        db.session.flush()
        self.order = Order(title="Poster", user_id=self.owner.id, category_id=self.category.id)
        db.session.add(self.order)
        db.session.commit()

    def staff(self, email, role="worker", assigned=True, active=True, deleted=False):
        from datetime import datetime
        user = User(email=email, password_hash="unused", role=role, is_active=active,
                    deleted_at=datetime.utcnow() if deleted else None)
        db.session.add(user)
        db.session.flush()
        if assigned:
            db.session.add(UserOrderCategoryPermission(user_id=user.id, category_id=self.category.id))
        db.session.commit()
        return user

    def content(self, kind):
        values = dict(order_id=self.order.id)
        if kind in (OrderFile, OrderPosterFile):
            values.update(original_name="test.pdf", stored_name="test.pdf", file_type="pdf")
        else:
            values.update(article_name="Paper")
        db.session.add(kind(**values))
        db.session.commit()

    def test_empty_order_does_not_send(self):
        self.staff("worker@example.test")
        with patch("notifications._send_new_order_email") as send:
            self.assertFalse(send_admin_order_notification(self.app, self.order))
            send.assert_not_called()

    def test_each_content_type_triggers_only_once(self):
        self.staff("worker@example.test")
        for kind in (OrderFile, OrderPosterFile, OrderProcurementArticle):
            with self.subTest(kind=kind.__name__):
                self.order.new_order_notified_at = None
                db.session.execute(text("DELETE FROM new_order_email_deliveries"))
                db.session.commit()
                self.content(kind)
                with patch("notifications._send_new_order_email", return_value=True) as send:
                    self.assertTrue(send_admin_order_notification(self.app, self.order))
                    self.assertFalse(send_admin_order_notification(self.app, self.order))
                    self.assertEqual(send.call_count, 1)
                for model in (OrderFile, OrderPosterFile, OrderProcurementArticle):
                    model.query.delete()
                db.session.commit()

    def test_only_active_assigned_staff_receive(self):
        self.staff("worker@example.test")
        self.staff("admin@example.test", role="admin")
        self.staff("otheradmin@example.test", role="admin", assigned=False)
        self.staff("inactive@example.test", active=False)
        self.staff("deleted@example.test", deleted=True)
        self.staff("user@example.test", role="user")
        denied = self.staff("denied@example.test")
        UserOrderCategoryPermission.query.filter_by(user_id=denied.id).first().can_manage = False
        other_category = OrderCategory(key="other", name="Other")
        db.session.add(other_category)
        db.session.flush()
        other = self.staff("other@example.test", assigned=False)
        db.session.add(UserOrderCategoryPermission(user_id=other.id, category_id=other_category.id))
        db.session.commit()
        self.content(OrderPosterFile)
        with patch("notifications._send_new_order_email", return_value=True) as send:
            self.assertTrue(send_admin_order_notification(self.app, self.order))
            self.assertEqual({call.args[3] for call in send.call_args_list},
                             {"worker@example.test", "admin@example.test"})

    def test_partial_failure_retries_only_failed_address(self):
        self.staff("first@example.test")
        self.staff("second@example.test")
        self.content(OrderPosterFile)
        with patch("notifications._send_new_order_email", side_effect=[True, False]):
            self.assertFalse(send_admin_order_notification(self.app, self.order))
        self.assertIsNone(self.order.new_order_notified_at)
        with patch("notifications._send_new_order_email", return_value=True) as send:
            self.assertTrue(send_admin_order_notification(self.app, self.order))
            self.assertEqual(send.call_count, 1)
            self.assertEqual(send.call_args.args[3], "second@example.test")

    def test_upgrade_suppresses_existing_orders_and_is_repeatable(self):
        db.session.execute(text("ALTER TABLE orders DROP COLUMN new_order_notified_at"))
        db.session.commit()
        ensure_new_order_notification_schema()
        ensure_new_order_notification_schema()
        db.session.expire_all()
        self.assertIsNotNone(self.order.new_order_notified_at)
        new = Order(title="New", user_id=self.owner.id, category_id=self.category.id)
        db.session.add(new)
        db.session.commit()
        self.assertIsNone(new.new_order_notified_at)

    def test_real_message_uses_owner_and_staff_language(self):
        worker = self.staff("worker@example.test")
        worker.language = "de"
        db.session.commit()
        self.content(OrderPosterFile)
        settings = dict(smtp_host="smtp.example.test", smtp_port=25,
                        smtp_from_address="neofab@example.test")
        with patch("notifications.load_app_settings", return_value=settings), \
             patch("notifications.is_email_action_enabled", return_value=True), \
             patch("notifications._send_message") as send, \
             patch("notifications.write_audit_log"):
            self.assertTrue(send_admin_order_notification(self.app, self.order))
            message = send.call_args.args[1]
            self.assertIn("Neuer Auftrag", message["Subject"])
            self.assertEqual(message["To"], worker.email)
            self.assertEqual(message["Reply-To"], self.owner.email)
            self.assertIn(self.owner.email, message.get_content())
            self.assertIn("/orders/", message.get_content())

    def test_disabled_or_missing_smtp_keeps_notification_pending(self):
        self.staff("worker@example.test")
        self.content(OrderPosterFile)
        for enabled in (True, False):
            with patch("notifications.load_app_settings", return_value={}), \
                 patch("notifications.is_email_action_enabled", return_value=enabled), \
                 patch("notifications._send_message") as send:
                self.assertFalse(send_admin_order_notification(self.app, self.order))
                self.assertIsNone(self.order.new_order_notified_at)
                send.assert_not_called()

    def test_content_routes_save_then_notify(self):
        import ast
        from datetime import datetime
        from io import BytesIO
        import os
        import tempfile
        from unittest.mock import Mock
        from flask import request, redirect, url_for, flash
        from sqlalchemy import func
        from werkzeug.utils import secure_filename
        import models

        # Execute the real route without importing the production app/database.
        source = (Path(__file__).resolve().parents[1] / "neofab/app.py").read_text(encoding="utf-8")
        node = next(n for n in ast.parse(source).body
                    if isinstance(n, ast.FunctionDef) and n.name == "order_detail")
        node.decorator_list = []
        namespace = vars(models).copy()
        namespace.update(
            app=self.app, request=request, current_user=self.owner, redirect=redirect,
            url_for=url_for, flash=flash, os=os, Path=Path, datetime=datetime, func=func,
            secure_filename=secure_filename, can_view_order=lambda *args: True,
            get_visible_order_tabs=lambda *args: ["general", "files", "posters", "articles"],
            inject_globals=lambda: {"t": lambda key: key},
            get_status_context=lambda trans: {}, is_plotter_order=lambda order: True,
            is_procurement_order=lambda order: True, normalize_poster_size=lambda size: "A1",
            save_poster_thumbnail=lambda *args: False, analyze_poster_coverage=lambda *args: None,
            update_order_file_preview=Mock(), write_audit_log=Mock(),
            sync_plotter_order_status_from_posters=Mock(),
            sync_procurement_order_status_from_articles=Mock(),
            ensure_procurement_article_position_numbers=Mock(),
            _send_relevant_order_status_email=Mock(),
            send_admin_order_notification=lambda app, order, labels: send_admin_order_notification(app, order, labels),
        )
        exec(compile(ast.Module(body=[node], type_ignores=[]), "app.py", "exec"), namespace)
        self.staff("worker@example.test")
        with tempfile.TemporaryDirectory() as folder:
            self.app.config.update(UPLOAD_FOLDER=folder, POSTER_UPLOAD_FOLDER=folder)
            actions = [
                ("upload_file", {"model_file": (BytesIO(b"solid test"), "test.stl")}, OrderFile),
                ("upload_poster_file", {"poster_file": (BytesIO(b"pdf"), "test.pdf")}, OrderPosterFile),
                ("create_procurement_article", {"article_name": "Paper"}, OrderProcurementArticle),
            ]
            for action, data, model in actions:
                with self.subTest(action=action):
                    self.order.new_order_notified_at = None
                    db.session.execute(text("DELETE FROM new_order_email_deliveries"))
                    db.session.commit()
                    def check_saved(*args):
                        self.assertEqual(model.query.filter_by(order_id=self.order.id).count(), 1)
                        self.assertFalse(db.session.new)
                        return True
                    with self.app.test_request_context("/orders/1", method="POST", data={"action": action, **data}), \
                         patch("notifications._send_new_order_email", side_effect=check_saved) as send:
                        response = namespace["order_detail"](self.order.id)
                        self.assertEqual(response.status_code, 302)
                        self.assertEqual(send.call_count, 1)
                    model.query.delete()
                    db.session.commit()

    def test_concurrent_requests_do_not_duplicate_delivery(self):
        from concurrent.futures import ThreadPoolExecutor
        import tempfile
        from threading import Barrier

        with tempfile.TemporaryDirectory() as folder:
            app = Flask("concurrent-notifications")
            app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///" + str(Path(folder) / "orders.db")
            db.init_app(app)
            with app.app_context():
                db.create_all()
                category = OrderCategory(key="plotter", name="Plotter")
                user = User(email="worker@example.test", password_hash="unused", role="worker")
                db.session.add_all([category, user])
                db.session.flush()
                order = Order(title="Concurrent", user_id=user.id, category_id=category.id)
                db.session.add(order)
                db.session.flush()
                order_id = order.id
                db.session.add_all([
                    UserOrderCategoryPermission(user_id=user.id, category_id=category.id),
                    OrderProcurementArticle(order_id=order.id, article_name="Paper"),
                ])
                db.session.commit()
            barrier = Barrier(2)

            def notify():
                with app.test_request_context("/"):
                    order = db.session.get(Order, order_id)
                    barrier.wait(timeout=5)
                    return send_admin_order_notification(app, order)

            try:
                with patch("notifications._send_new_order_email", return_value=True) as send:
                    with ThreadPoolExecutor(max_workers=2) as executor:
                        results = list(executor.map(lambda _: notify(), range(2)))
                    self.assertEqual(results.count(True), 1)
                    self.assertEqual(send.call_count, 1)
            finally:
                with app.app_context():
                    db.session.remove()
                    db.engine.dispose()


if __name__ == "__main__":
    unittest.main()
