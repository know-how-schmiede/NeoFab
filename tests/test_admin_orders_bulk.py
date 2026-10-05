"""Bulk order actions, using an isolated database and temporary uploads."""
import json
from datetime import datetime
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from flask import Flask
from flask_login import LoginManager
from jinja2 import ChoiceLoader, DictLoader

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "neofab"))
from models import db, Order, OrderMessage, User
from routes.admin import create_admin_blueprint

ROOT = Path(__file__).resolve().parents[1]


class BulkOrderTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.app = Flask(__name__, template_folder=str(ROOT / "neofab/templates"))
        self.app.config.update(TESTING=True, SECRET_KEY="test", SQLALCHEMY_DATABASE_URI="sqlite://")
        for key in ("UPLOAD_FOLDER", "IMAGE_UPLOAD_FOLDER", "VIDEO_UPLOAD_FOLDER",
                    "GCODE_UPLOAD_FOLDER", "POSTER_UPLOAD_FOLDER", "PROCUREMENT_NOTE_UPLOAD_FOLDER"):
            self.app.config[key] = str(Path(self.temp.name) / key)
        self.app.config["NEOFAB_LOG_FOLDER"] = str(Path(self.temp.name) / "logs")
        db.init_app(self.app)
        login = LoginManager(self.app)
        login.user_loader(lambda user_id: db.session.get(User, int(user_id)))
        self.translations = json.loads((ROOT / "i18n/de.json").read_text())
        self.app.register_blueprint(create_admin_blueprint(lambda: self.translations.__getitem__))
        self.app.add_url_rule('/orders/<int:order_id>', 'order_detail', lambda order_id: '')
        self.app.jinja_loader = ChoiceLoader([
            DictLoader({'base.html': '{% block content %}{% endblock %}'}), self.app.jinja_loader,
        ])
        self.app.jinja_env.globals.update(t=self.translations.__getitem__, status_styles={},
                                         status_labels={}, fmt_datetime=str)
        self.context = self.app.app_context()
        self.context.push()
        self.addCleanup(self.context.pop)
        self.addCleanup(db.engine.dispose)
        self.addCleanup(db.session.remove)
        db.create_all()
        db.session.add(User(id=1, email="admin@example.test", password_hash="unused", role="admin"))
        db.session.add_all(Order(id=i, title=f"Order {i}", user_id=1) for i in range(1, 5))
        db.session.add(OrderMessage(order_id=2, user_id=1, content="test"))
        db.session.commit()
        self.client = self.app.test_client()
        with self.client.session_transaction() as session:
            session['_user_id'] = '1'
            session['_fresh'] = True

    def post(self, action="archive", ids=(1, 2), confirmed="yes"):
        return self.client.post('/admin/orders/bulk', data={
            'action': action, 'order_ids': [str(i) for i in ids], 'confirmed': confirmed,
        })

    def test_archive_only_selected_and_preserve_existing_archive_date(self):
        old_date = datetime(2020, 1, 1)
        db.session.get(Order, 2).is_archived = True
        db.session.get(Order, 2).archived_at = old_date
        db.session.commit()
        self.assertEqual(self.post(ids=(1, 2, 1)).status_code, 302)
        self.assertTrue(db.session.get(Order, 1).is_archived)
        self.assertEqual(db.session.get(Order, 2).archived_at, old_date)
        self.assertFalse(db.session.get(Order, 3).is_archived)
        with self.client.session_transaction() as session:
            self.assertIn('Archiviert: 1. Bereits archiviert: 1. Fehlgeschlagen: 0.', str(session['_flashes']))

    def test_invalid_or_unconfirmed_selection_changes_nothing(self):
        for kwargs in ({'confirmed': ''}, {'ids': ()}, {'ids': (1, 'invalid')},
                       {'ids': (1, 999)}, {'ids': (-1,)}, {'action': 'unknown'}):
            with self.subTest(kwargs=kwargs):
                self.assertEqual(self.post(**kwargs).status_code, 302)
                self.assertEqual(Order.query.filter_by(is_archived=True).count(), 0)
                self.assertEqual(Order.query.count(), 4)

    def test_delete_selected_records_related_data_and_files(self):
        root = Path(self.app.config['UPLOAD_FOLDER'])
        for i in range(1, 5):
            folder = root / f'order_{i}'
            folder.mkdir(parents=True)
            (folder / 'part.stl').write_text('test')
        self.assertEqual(self.post('delete', (2, 3)).status_code, 302)
        self.assertEqual([o.id for o in Order.query.order_by(Order.id)], [1, 4])
        self.assertEqual(OrderMessage.query.count(), 0)
        self.assertFalse((root / 'order_2').exists())
        self.assertFalse((root / 'order_3').exists())
        self.assertTrue((root / 'order_1/part.stl').exists())
        self.assertTrue((root / 'order_4/part.stl').exists())

    def test_delete_failure_is_reported_and_other_orders_continue(self):
        root = Path(self.app.config['UPLOAD_FOLDER'])
        (root / 'order_1').mkdir(parents=True)
        with patch('routes.admin.shutil.rmtree', side_effect=OSError('test failure')):
            self.post('delete', (1, 2))
        self.assertIsNotNone(db.session.get(Order, 1))
        self.assertIsNone(db.session.get(Order, 2))
        with self.client.session_transaction() as session:
            self.assertIn('Gelöscht: 1. Fehlgeschlagen: 1.', str(session['_flashes']))

    def test_admin_required(self):
        db.session.get(User, 1).role = 'user'
        db.session.commit()
        self.assertEqual(self.post('delete').status_code, 403)
        self.assertEqual(Order.query.count(), 4)

    def test_post_required(self):
        self.assertEqual(self.client.get('/admin/orders/bulk').status_code, 405)

    def test_single_delete_still_works(self):
        self.assertEqual(self.client.post('/admin/orders/2/delete').status_code, 302)
        self.assertIsNone(db.session.get(Order, 2))
        self.assertEqual(OrderMessage.query.count(), 0)

    def test_management_template_renders_controls_and_escapes_titles(self):
        db.session.get(Order, 1).title = '<script>alert(1)</script>'
        db.session.commit()
        response = self.client.get('/admin/orders')
        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn('Auswahl umkehren', html)
        self.assertEqual(html.count('class="form-check-input order-selection"'), 4)
        self.assertIn('name="confirmed" value="yes"', html)
        self.assertNotIn('<script>alert(1)</script>', html)


if __name__ == '__main__':
    unittest.main()
