"""Workflows réels via client Flask, SQLite éphémère ou schéma PostgreSQL annulé."""
import copy
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from uuid import uuid4
from zipfile import ZipFile
from unittest.mock import patch, MagicMock

import yaml
from sqlalchemy import create_engine, event, select, func, text
from sqlalchemy.orm import Session, sessionmaker
from werkzeug.security import generate_password_hash

from animmalle import create_app
from animmalle.config import CONFIG_PATH, load_database_url, load_settings
from animmalle.models import Base, Thesaurus, Sequence, Animation

ROOT = Path(__file__).resolve().parents[2]


class ApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.password_hash = generate_password_hash('test-password')
        if os.environ.get('ANIMMALLE_TEST_POSTGRES') == '1':
            cls.original_snapshot = cls.public_snapshot()

    @classmethod
    def public_snapshot(cls):
        engine = create_engine(load_database_url(), hide_parameters=True)
        try:
            with engine.connect() as connection, connection.begin():
                connection.execute(text('SET TRANSACTION READ ONLY'))
                digest = hashlib.sha256()
                for name in sorted(Base.metadata.tables):
                    rows = connection.execute(text(f'SELECT * FROM public.{name} ORDER BY id')).all()
                    digest.update(json.dumps([list(row) for row in rows], default=str, ensure_ascii=False).encode())
                schemas = connection.execute(text("SELECT schema_name FROM information_schema.schemata WHERE schema_name LIKE 'test_api_%' ORDER BY schema_name")).scalars().all()
                return digest.hexdigest(), schemas
        finally:
            engine.dispose()

    @classmethod
    def tearDownClass(cls):
        if os.environ.get('ANIMMALLE_TEST_POSTGRES') == '1':
            if cls.public_snapshot() != cls.original_snapshot:
                raise AssertionError('Les données publiques ou les schémas temporaires ont changé.')

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        settings = yaml.safe_load((ROOT / 'installation/config_principal.example.yaml').read_text())
        settings['backend'].update(secret_key='x' * 64, cookie_secure=False)
        settings['public'] = {'frontend_url': 'http://front.test', 'api_url': 'http://api.test'}
        settings['auth'] = {'mode': 'local', 'admin_groups': ['admin'], 'users': [
            {'login': name, 'name': name, 'groups': ['admin'] if name == 'admin' else [], 'password_hash': self.password_hash}
            for name in ('admin', 'alice', 'bob')]}
        settings['paths'] = {key: str(root / key) for key in settings['paths']}
        self.config_path = root / 'config.yaml'
        self.config_path.write_text(yaml.safe_dump(settings))
        self.settings = settings
        self.connection = None
        if os.environ.get('ANIMMALLE_TEST_POSTGRES') == '1':
            engine = create_engine(load_database_url(), hide_parameters=True)
            self.addCleanup(engine.dispose)
            self.connection = engine.connect()
            self.addCleanup(self.connection.close)
            transaction = self.connection.begin()
            self.addCleanup(transaction.rollback)
            schema = 'test_api_' + uuid4().hex
            self.connection.execute(text(f'CREATE SCHEMA "{schema}"'))
            self.connection.execute(text(f'SET LOCAL search_path TO "{schema}"'))
            # Migration réelle dans un schéma isolé, jamais dans public.
            from alembic.migration import MigrationContext
            from alembic.operations import Operations
            spec = importlib.util.spec_from_file_location('initial_api_test', ROOT / 'backend/migrations/versions/0001_initial.py')
            migration = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(migration)
            migration.op = Operations(MigrationContext.configure(self.connection))
            migration.upgrade()
            self.bind = self.connection
        else:
            engine = create_engine('sqlite:///' + str(root / 'test.sqlite'))
            self.addCleanup(engine.dispose)
            @event.listens_for(engine, 'connect')
            def foreign_keys(connection, _):
                connection.execute('PRAGMA foreign_keys=ON')
            Base.metadata.create_all(engine)  # Uniquement base jetable de test.
            self.bind = engine
        self.app = create_app(self.config_path, engine=self.bind)
        self.app.config['TESTING'] = True
        if self.connection is not None:
            self.app.extensions['db_sessions'] = sessionmaker(self.connection, join_transaction_mode='create_savepoint', expire_on_commit=False)
        self.client = self.app.test_client()
        with self.db() as db:
            for key, family in enumerate(['ref.duree', 'ref.duree_seq', 'ref.modalites', 'ref.approches', 'ref.type_seq', 'ref.thematiques', 'ref.type_mat', 'ref.type_outil', 'ref.difficulte'], 1):
                db.add(Thesaurus(id=100 + key, label='Catégorie ' + family, reference='', code=family))
                db.add(Thesaurus(id=key, label=family, reference=family, code='briseglace' if key == 8 else ''))
            if self.connection is not None:
                db.execute(text('ALTER SEQUENCE thesaurus_id_seq RESTART WITH 200'))
            db.commit()
        self.login('alice')

    def db(self):
        return self.app.extensions['db_sessions']()

    def login(self, name):
        self.token = self.client.get('/api/auth/session').json['csrf_token']
        response = self.mutate('post', '/api/auth/login', {'login': name, 'password': 'test-password'})
        self.assertEqual(response.status_code, 200, response.json)
        self.token = response.json['csrf_token']

    def mutate(self, method, path, json_data=None, **kwargs):
        if json_data is not None:
            kwargs['json'] = json_data
        return getattr(self.client, method)(path, headers={'X-CSRF-Token': self.token}, **kwargs)

    def animation_data(self):
        return {'titre': 'Une animation', 'statut': 3, 'fk_duree_id': 1, 'tags': [6, 6],
                'sequences': [{'titre': 'Introduction', 'description': 'Texte <&>', 'fk_duree_id': 2,
                               'fk_modalite_id': 3, 'fk_approche_id': 4, 'fk_type_seq_id': 5, 'materiel': []}]}

    def create_animation(self):
        response = self.mutate('post', '/api/animations', self.animation_data())
        self.assertEqual(response.status_code, 201, response.json)
        return response.json

    def material_data(self):
        return {'nom': 'Un média', 'fk_type_mat_id': 7, 'thematiques': [6, 6]}

    def test_session_csrf_cors_and_logout(self):
        self.assertEqual(self.client.post('/api/animations', json=self.animation_data()).status_code, 403)
        response = self.client.get('/api/animations', headers={'Origin': 'http://front.test'})
        self.assertEqual(response.headers['Access-Control-Allow-Origin'], 'http://front.test')
        self.assertEqual(self.client.get('/api/animations', headers={'Origin': 'http://evil.test'}).status_code, 403)
        response = self.mutate('post', '/api/auth/logout')
        self.assertEqual(response.status_code, 204)
        self.assertEqual(self.client.get('/api/animations').status_code, 401)
        self.assertEqual(self.client.get('/api/auth/session').status_code, 200)

    def test_login_invalid_and_session_rotation(self):
        previous = self.token
        self.assertEqual(self.mutate('post', '/api/auth/login', {'login': 'alice', 'password': 'bad'}).status_code, 401)
        self.login('bob')
        self.assertNotEqual(previous, self.token)
        self.assertEqual(self.client.post('/api/auth/logout', headers={'X-CSRF-Token': previous}).status_code, 403)

    def test_animation_lifecycle_permissions_and_comments(self):
        item = self.create_animation()
        key = item['id']
        self.assertEqual(set(item['tags']), {1, 6})
        comment = self.mutate('post', f'/api/animations/{key}/comments', {'commentaire': 'Bonjour'})
        self.assertEqual(comment.status_code, 201)
        self.login('bob')
        self.assertEqual(self.client.get(f'/api/animations/{key}').status_code, 403)
        self.assertEqual(self.client.get('/api/animations').json['total'], 0)
        self.assertEqual(self.mutate('put', f'/api/animations/{key}', self.animation_data()).status_code, 403)
        self.login('admin')
        self.assertEqual(self.mutate('post', f'/api/animations/{key}/validate').status_code, 200)
        self.login('bob')
        self.assertEqual(self.client.get(f'/api/animations/{key}').status_code, 200)
        self.assertEqual(self.mutate('delete', f"/api/animations/{key}/comments/{comment.json['id']}").status_code, 403)
        self.login('alice')
        self.assertEqual(self.mutate('delete', f"/api/animations/{key}/comments/{comment.json['id']}").status_code, 204)
        self.assertEqual(self.mutate('delete', f'/api/animations/{key}').status_code, 403)
        self.login('admin')
        self.assertEqual(self.mutate('delete', f'/api/animations/{key}').status_code, 204)
        with self.db() as db:
            self.assertEqual(db.scalar(select(func.count()).select_from(Sequence)), 0)

    def test_sequences_update_reorder_remove_and_rollback(self):
        item = self.create_animation()
        key = item['id']
        data = self.animation_data()
        data['sequences'][0]['id'] = item['sequences'][0]['id']
        data['sequences'].append({**data['sequences'][0], 'titre': 'Deuxième'})
        data['sequences'][1].pop('id')
        response = self.mutate('put', f'/api/animations/{key}', data)
        self.assertEqual(response.status_code, 200, response.json)
        data['sequences'] = response.json['sequences'][::-1]
        response = self.mutate('put', f'/api/animations/{key}', data)
        self.assertEqual([s['titre'] for s in response.json['sequences']], ['Deuxième', 'Introduction'])
        bad = copy.deepcopy(data)
        bad['titre'] = 'Ne doit pas être enregistré'
        bad['sequences'][1]['fk_duree_id'] = 99999
        self.assertEqual(self.mutate('put', f'/api/animations/{key}', bad).status_code, 422)
        self.assertEqual(self.client.get(f'/api/animations/{key}').json['titre'], data['titre'])
        data['sequences'] = []
        self.assertEqual(self.mutate('put', f'/api/animations/{key}', data).status_code, 200)
        with self.db() as db:
            self.assertEqual(db.scalar(select(func.count()).select_from(Sequence)), 0)

    def test_foreign_sequence_and_validation_refused(self):
        first, second = self.create_animation(), self.create_animation()
        data = self.animation_data()
        data['sequences'][0]['id'] = first['sequences'][0]['id']
        self.assertEqual(self.mutate('put', f"/api/animations/{second['id']}", data).status_code, 422)
        data = self.animation_data()
        data['statut'] = 1
        self.assertEqual(self.mutate('post', '/api/animations', data).status_code, 403)
        data['statut'] = True
        self.assertEqual(self.mutate('post', '/api/animations', data).status_code, 422)
        data = self.animation_data()
        data['auteurs'] = 'admin'
        self.assertEqual(self.mutate('post', '/api/animations', data).status_code, 422)

    def test_material_file_search_delete_and_export(self):
        response = self.mutate('post', '/api/materials', content_type='multipart/form-data',
                               data={'data': json.dumps(self.material_data()), 'file': (io.BytesIO(b'%PDF test'), '../../test.pdf')})
        self.assertEqual(response.status_code, 201, response.json)
        key = response.json['id']
        self.assertNotIn('url', response.json)
        response = self.client.get(f'/api/materials/{key}/file')
        self.assertEqual(response.data, b'%PDF test')
        response.close()
        self.assertEqual(self.client.get('/api/materials?kind=media&tag=6').json['total'], 1)
        self.assertEqual(self.mutate('delete', f'/api/materials/{key}').status_code, 403)
        response = self.client.get(f'/api/materials/{key}/download')
        with ZipFile(io.BytesIO(response.data)) as archive:
            self.assertTrue(any(name.endswith('.odt') for name in archive.namelist()))
            self.assertTrue(any(name.startswith('medias/') for name in archive.namelist()))
        self.login('admin')
        self.assertEqual(self.mutate('delete', f'/api/materials/{key}').status_code, 204)
        self.assertTrue(list(Path(self.settings['paths']['uploads']).glob('*.pdf')))

    def test_material_relations_and_invalid_upload(self):
        result = self.mutate('post', '/api/materials', self.material_data())
        key = result.json['id']
        data = self.animation_data()
        data['sequences'][0]['materiel'] = [key]
        anim = self.mutate('post', '/api/animations', data).json
        self.login('admin')
        response = self.mutate('post', f'/api/materials/{key}/file',
                               data={'file': (io.BytesIO(b'bad'), 'test.exe')})
        self.assertEqual(response.status_code, 422)
        self.assertEqual(self.mutate('delete', f'/api/materials/{key}').status_code, 204)
        self.assertEqual(self.client.get(f"/api/animations/{anim['id']}").json['sequences'][0]['materiel'], [])

    def test_thesaurus_duplicates_references_and_delete(self):
        self.assertEqual(self.mutate('post', '/api/thesaurus', {'label': 'Tag', 'reference': 'ref.thematiques'}).status_code, 403)
        self.login('admin')
        data = {'label': 'Tag', 'reference': 'ref.thematiques'}
        created = self.mutate('post', '/api/thesaurus', data)
        self.assertEqual(created.status_code, 201)
        self.assertEqual(self.mutate('post', '/api/thesaurus', data).status_code, 409)
        self.assertEqual(self.mutate('delete', '/api/thesaurus/106').status_code, 409)
        self.assertEqual(self.mutate('delete', f"/api/thesaurus/{created.json['id']}").status_code, 204)
        self.create_animation()
        self.assertEqual(self.mutate('delete', '/api/thesaurus/1').status_code, 409)

    def test_pages_overlay_revisions_and_sanitization(self):
        legacy = Path(self.settings['paths']['legacy_pages']) / 'notice'
        legacy.mkdir(parents=True)
        (legacy / 'current.md').write_text('Ancienne notice')
        self.assertEqual(self.client.get('/api/pages/notice').json['contenu'], 'Ancienne notice')
        self.assertEqual(self.mutate('put', '/api/pages/notice', {'contenu': 'Test'}).status_code, 403)
        self.login('admin')
        response = self.mutate('put', '/api/pages/notice', {'contenu': '# Nouveau\n<script>alert(1)</script>[clic](javascript:alert(1))'})
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('<script', response.json['html'])
        self.assertNotIn('javascript:', response.json['html'])
        self.assertEqual((legacy / 'current.md').read_text(), 'Ancienne notice')
        self.assertEqual(len(list((Path(self.settings['paths']['pages']) / 'notice').glob('rev_*.md'))), 1)
        self.assertEqual(self.client.get('/api/pages/bad.name').status_code, 404)

    def test_export_missing_files_and_odt_xml(self):
        from animmalle.models import MatPeda
        material = self.mutate('post', '/api/materials', self.material_data()).json
        with self.db() as db:
            db.get(MatPeda, material['id']).url = '/outside/nonexistent.pdf'
            db.commit()
        data = self.animation_data()
        data['sequences'][0]['materiel'] = [material['id']]
        item = self.mutate('post', '/api/animations', data).json
        response = self.client.get(f"/api/animations/{item['id']}/download")
        from xml.etree import ElementTree
        with ZipFile(io.BytesIO(response.data)) as archive:
            self.assertEqual(json.loads(archive.read('donnees.json'))['id'], item['id'])
            self.assertEqual(json.loads(archive.read('fichiers_absents.json')), [material['id']])
            odt = next(name for name in archive.namelist() if name.endswith('.odt'))
            with ZipFile(io.BytesIO(archive.read(odt))) as document:
                ElementTree.fromstring(document.read('content.xml'))
                self.assertEqual(document.infolist()[0].filename, 'mimetype')
                self.assertEqual(document.infolist()[0].compress_type, 0)

    def test_search_stats_authors_errors(self):
        self.create_animation()
        response = self.client.get('/api/animations?tag=6&page_size=1')
        self.assertEqual(response.json['items'][0]['pertinence']['matched'], 1)
        self.assertEqual(self.client.get('/api/animations?tag=999').json['total'], 0)
        self.assertEqual(self.client.get('/api/animations?page_size=0').status_code, 422)
        self.assertEqual(self.client.get('/api/materials?type=no').status_code, 422)
        self.assertEqual(self.client.get('/api/stats').status_code, 200)
        self.assertEqual(self.client.get('/api/authors?q=ali').json['items'], ['alice'])
        self.assertEqual(self.client.get('/api/materials/999').status_code, 404)
        self.assertEqual(self.client.get('/api/health').json['status'], 'ok')
        self.assertEqual(self.client.get('/installation/config_principal.yaml').status_code, 404)

    def test_notification_and_proxy(self):
        self.login('admin')
        self.app.extensions['settings']['mail'] = {
            'enabled': True, 'host': 'smtp.test', 'port': 587, 'starttls': True,
            'sender': 'app@test.org', 'recipients': ['admin@test.org']}
        with patch('animmalle.notifications.smtplib.SMTP') as smtp:
            response = self.mutate('put', '/api/pages/notice', {'contenu': 'Notice'})
            self.assertEqual(response.json['notification'], 'sent')
            smtp.return_value.__enter__.return_value.send_message.assert_called_once()
        with patch('animmalle.notifications.smtplib.SMTP', side_effect=OSError):
            response = self.mutate('put', '/api/pages/notice', {'contenu': 'Autre notice'})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json['notification'], 'failed')
        self.assertEqual(self.app.wsgi_app.x_for, 0)
        self.assertEqual(self.app.wsgi_app.x_host, 0)

    def test_ldap_bind_filter_groups_and_directory(self):
        import ldap3
        from animmalle.auth import authenticate
        config = yaml.safe_load((ROOT / 'installation/config_principal.example.yaml').read_text())['auth']
        self.app.extensions['settings']['auth'] = config
        entry = MagicMock()
        entry.entry_attributes_as_dict = {'cn': ['Alice Nom'], 'memberOf': ['CN=Administrateurs,OU=Groupes,DC=example,DC=org']}
        with self.app.app_context(), patch('ldap3.Connection') as factory:
            connection = factory.return_value
            connection.bind.return_value = True
            connection.search.return_value = True
            connection.entries = [entry]
            user = authenticate('alice*)(cn=*)', 'test')
            self.assertEqual(user, {'name': 'Alice Nom', 'groups': ['Administrateurs']})
            ldap_filter = connection.search.call_args.args[1]
            self.assertIn(r'\2a', ldap_filter)
            connection.unbind.assert_called_once()
            connection.bind.return_value = False
            self.assertIsNone(authenticate('alice', 'bad'))
        self.app.extensions['settings']['auth'] = self.settings['auth']
        response = self.client.get('/api/users?q=al')
        self.assertEqual(response.json['items'], ['alice'])
        self.assertEqual(self.client.get('/api/users?q=a').status_code, 422)

    def test_configuration_validation(self):
        import runpy
        with patch('animmalle.config.load_settings', return_value=load_settings(self.config_path)):
            config = runpy.run_path(str(ROOT / 'backend/gunicorn.conf.py'))
            self.assertEqual(config['bind'], '127.0.0.1:8000')
            self.assertEqual(config['forwarded_allow_ips'], '')
        settings = copy.deepcopy(self.settings)
        settings['proxy']['x_for'] = True
        self.config_path.write_text(yaml.safe_dump(settings))
        with self.assertRaises(ValueError):
            load_settings(self.config_path)
        settings = copy.deepcopy(self.settings)
        settings['paths']['uploads'] = 'ancien_animalle/static/upload'
        self.config_path.write_text(yaml.safe_dump(settings))
        with self.assertRaises(ValueError):
            load_settings(self.config_path)


if __name__ == '__main__':
    unittest.main()
