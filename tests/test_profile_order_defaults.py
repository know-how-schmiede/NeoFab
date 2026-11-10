"""Exercise profile preferences without starting the production application."""
import ast
from pathlib import Path
import sys
import unittest
from types import SimpleNamespace

from flask import Flask, request, session
from sqlalchemy import text

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'neofab'))
import models


def load_function(name, namespace):
    tree = ast.parse((ROOT / 'neofab/app.py').read_text(encoding='utf-8'))
    node = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == name)
    node.decorator_list = []
    exec(compile(ast.Module(body=[node], type_ignores=[]), 'app.py', 'exec'), namespace)
    return namespace[name]


class ProfileOrderDefaultsTests(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.config.update(SECRET_KEY='test', SQLALCHEMY_DATABASE_URI='sqlite://')
        models.db.init_app(self.app)
        self.context = self.app.app_context()
        self.context.push()
        self.addCleanup(self.context.pop)
        self.addCleanup(models.db.engine.dispose)
        self.addCleanup(models.db.session.remove)
        models.db.create_all()

    def test_profile_save_for_roles_and_both_values(self):
        for role in ('admin', 'worker', 'user'):
            user = models.User(email=role+'@example.test', password_hash='unused', role=role)
            models.db.session.add(user)
            models.db.session.commit()
            ns = vars(models).copy()
            ns.update(current_user=user, request=request, session=session,
                      inject_globals=lambda: {'t': lambda key: key},
                      flash=lambda *args: None, redirect=lambda url: url,
                      url_for=lambda endpoint: '/'+endpoint, SUPPORTED_LANGS=('en', 'de', 'fr'))
            profile = load_function('profile', ns)
            for enabled in (True, False):
                data = {'email': user.email}
                if enabled:
                    data['dashboard_hide_completed'] = 'on'
                with self.app.test_request_context('/profile', method='POST', data=data):
                    session['dashboard_filter_hide_completed'] = '1'
                    self.assertEqual(profile(), '/profile')
                    self.assertEqual(user.dashboard_hide_completed, enabled and role != 'user')
                    if role != 'user':
                        self.assertNotIn('dashboard_filter_hide_completed', session)

    def test_default_session_override_and_explicit_query(self):
        user = SimpleNamespace(role='admin', dashboard_hide_completed=True)
        ns = dict(request=request, session=session, current_user=user,
                  dashboard_filter_session_keys={'hide_completed': 'dashboard_filter_hide_completed'})
        get_filter = load_function('_get_persistent_dashboard_filter', ns)
        for role in ('admin', 'worker', 'user'):
            user.role = role
            with self.app.test_request_context('/'):
                self.assertEqual(get_filter('hide_completed'), '0' if role == 'user' else '1')
                session['dashboard_filter_hide_completed'] = '0'
                self.assertEqual(get_filter('hide_completed'), '0')
            with self.app.test_request_context('/?hide_completed=1'):
                self.assertEqual(get_filter('hide_completed'), '1')
                self.assertEqual(session['dashboard_filter_hide_completed'], '1')
        user.role = 'admin'
        user.dashboard_hide_completed = False
        with self.app.test_request_context('/'):
            self.assertEqual(get_filter('hide_completed'), '0')

    def test_existing_database_migration_is_repeatable(self):
        models.db.session.execute(text('DROP TABLE user'))
        models.db.session.execute(text('CREATE TABLE user (id INTEGER PRIMARY KEY)'))
        models.db.session.execute(text('INSERT INTO user (id) VALUES (1)'))
        models.db.session.commit()
        migrate = load_function('ensure_user_preference_columns', dict(db=models.db, text=text, app=self.app))
        migrate()
        migrate()
        self.assertEqual(models.db.session.execute(text('SELECT dashboard_hide_completed FROM user')).scalar(), 0)
