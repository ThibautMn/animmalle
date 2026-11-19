"""Workflows réels via client Flask, SQLite éphémère ou schéma PostgreSQL annulé."""
import copy
import hashlib
import importlib.util
import io
import shutil
import subprocess
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
from animmalle.models import APPLICATION_TABLES, Base, TaxonMedia, Thesaurus, Sequence, Animation

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
                for name in sorted(set(Base.metadata.tables) - APPLICATION_TABLES):
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
            spec = importlib.util.spec_from_file_location('taxon_api_test', ROOT / 'backend/migrations/versions/0003_taxon_media.py')
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
            for key, family in enumerate(['ref.duree', 'ref.modalites', 'ref.approches', 'ref.type_seq', 'ref.thematiques', 'ref.type_mat', 'ref.type_outil', 'ref.difficulte'], 1):
                db.add(Thesaurus(id=100 + key, label='Catégorie ' + family, reference='', code=family))
                db.add(Thesaurus(id=key, label=family, reference=family, code='briseglace' if key == 7 else ''))
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
        return {'titre': 'Une animation', 'statut': 3, 'fk_duree_id': 1, 'tags': [5, 5],
                'sequences': [{'titre': 'Introduction', 'description': 'Texte <&>', 'duree_minutes': 10,
                               'fk_modalite_id': 2, 'fk_approche_id': 3, 'fk_type_seq_id': 4, 'materiel': []}]}

    def create_animation(self):
        response = self.mutate('post', '/api/animations', self.animation_data())
        self.assertEqual(response.status_code, 201, response.json)
        return response.json

    def material_data(self):
        return {'nom': 'Un média', 'fk_type_mat_id': 6, 'thematiques': [5, 5]}

    def test_session_csrf_cors_and_logout(self):
        self.assertEqual(self.client.post('/api/animations', json=self.animation_data()).status_code, 403)
        response = self.client.get('/api/animations', headers={'Origin': 'http://front.test'})
        self.assertEqual(response.headers['Access-Control-Allow-Origin'], 'http://front.test')
        self.assertEqual(response.headers['Access-Control-Expose-Headers'], 'Content-Disposition')
        self.assertEqual(self.client.get('/api/animations', headers={'Origin': 'http://evil.test'}).status_code, 403)
        response = self.mutate('post', '/api/auth/logout')
        self.assertEqual(response.status_code, 204)
        self.assertEqual(self.client.get('/api/animations').status_code, 401)
        self.assertEqual(self.client.get('/api/auth/session').status_code, 200)

    def enable_oidc(self, only=False):
        self.settings['auth']['oidc'] = {'provider_name': 'Échange', 'discovery_url': 'http://idp.test/.well-known',
                                         'client_id': 'cid', 'client_secret': 'secret', 'only_oidc_connexion': only}
        self.config_path.write_text(yaml.safe_dump(self.settings))
        self.client = create_app(self.config_path, engine=self.app.extensions['db_engine']).test_client()
        self.client.application.config['TESTING'] = True
        self.client.application.extensions['db_sessions'] = self.app.extensions['db_sessions']
        self.token = self.client.get('/api/auth/session').json['csrf_token']

    def test_oidc_disabled_by_default(self):
        self.assertEqual(self.client.get('/api/auth/oidc/config').json,
                         {'enabled': False, 'provider': 'OpenID', 'only': False})
        self.assertEqual(self.client.get('/api/auth/oidc/authorize?state=abcdefgh&code_challenge=' + 'a' * 43).status_code, 400)

    def test_oidc_login_flow_and_only_mode(self):
        from unittest import mock
        self.enable_oidc(only=True)
        self.assertEqual(self.client.get('/api/auth/oidc/config').json, {'enabled': True, 'provider': 'Échange', 'only': True})
        # le formulaire est refusé, même avec de bons identifiants
        self.assertEqual(self.mutate('post', '/api/auth/login', {'login': 'alice', 'password': 'test-password'}).status_code, 403)
        discovery = {'authorization_endpoint': 'http://idp.test/authorize'}
        with mock.patch('animmalle.oidc.discovery', return_value=discovery):
            url = self.client.get('/api/auth/oidc/authorize?state=abcdefgh&code_challenge=' + 'a' * 43).json['url']
            self.assertIn('code_challenge_method=S256', url)
            self.assertIn('redirect_uri=http%3A%2F%2Ffront.test%2Foidc', url)
            self.assertNotIn('prompt=none', url)
            silent = self.client.get('/api/auth/oidc/authorize?silent=1&state=abcdefgh&code_challenge=' + 'a' * 43).json['url']
            self.assertIn('prompt=none', silent)
            self.assertEqual(self.client.get('/api/auth/oidc/authorize?state=abcdefgh&code_challenge=court').status_code, 400)
        body = {'code': 'c', 'code_verifier': 'v' * 43}
        self.assertEqual(self.mutate('post', '/api/auth/oidc/callback', {'code': 'c'}).status_code, 400)
        with mock.patch('animmalle.oidc.exchange_code', return_value={'preferred_username': 'inconnu'}):
            self.assertEqual(self.mutate('post', '/api/auth/oidc/callback', body).status_code, 403)
        with mock.patch('animmalle.oidc.exchange_code', return_value={'preferred_username': 'admin', 'email': 'alice@x'}):
            response = self.mutate('post', '/api/auth/oidc/callback', body)
        self.assertEqual(response.status_code, 200, response.json)
        self.assertEqual(response.json['user']['name'], 'admin')
        self.assertTrue(response.json['is_admin'])
        self.assertEqual(self.client.get('/api/animations').status_code, 200)

    def test_oidc_with_password_form_still_allowed(self):
        self.enable_oidc(only=False)
        self.assertFalse(self.client.get('/api/auth/oidc/config').json['only'])
        self.login('alice')

    def test_login_invalid_and_session_rotation(self):
        previous = self.token
        self.assertEqual(self.mutate('post', '/api/auth/login', {'login': 'alice', 'password': 'bad'}).status_code, 401)
        self.login('bob')
        self.assertNotEqual(previous, self.token)
        self.assertEqual(self.client.post('/api/auth/logout', headers={'X-CSRF-Token': previous}).status_code, 403)

    def test_animation_lifecycle_permissions_and_comments(self):
        item = self.create_animation()
        key = item['id']
        self.assertEqual(set(item['tags']), {1, 5})
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
        bad['sequences'][1]['duree_minutes'] = 0
        self.assertEqual(self.mutate('put', f'/api/animations/{key}', bad).status_code, 422)
        self.assertEqual(self.client.get(f'/api/animations/{key}').json['titre'], data['titre'])
        data['sequences'] = []
        self.assertEqual(self.mutate('put', f'/api/animations/{key}', data).status_code, 200)
        with self.db() as db:
            self.assertEqual(db.scalar(select(func.count()).select_from(Sequence)), 0)

    def test_sequences_list_filters_visibility_and_copy(self):
        item = self.create_animation()
        with self.db() as db:
            db.add(Thesaurus(id=300, label='Développement', reference='ref.type_seq', code=''))
            db.commit()
        data = self.animation_data()
        data['sequences'][0].update(titre='Jeu du castor', fk_type_seq_id=300)
        other = self.mutate('post', '/api/animations', data).json
        result = self.client.get('/api/sequences').json
        self.assertEqual(result['total'], 2)
        self.assertEqual(result['items'][0]['titre'], 'Introduction')
        self.assertEqual(result['items'][0]['animation']['id'], item['id'])
        self.assertEqual(self.client.get('/api/sequences?q=jeu&q=castor').json['total'], 1)
        self.assertEqual(self.client.get('/api/sequences?q=jeu&q=absent').json['total'], 0)
        self.assertEqual(self.client.get('/api/sequences?type=300').json['total'], 1)
        self.assertEqual(self.client.get('/api/sequences?type=300&approche=99').json['total'], 0)
        self.assertEqual(self.client.get('/api/sequences?type=x').status_code, 422)
        # Copie : une séquence sans identifiant crée une séquence distincte, l'originale reste intacte.
        copy_data = self.animation_data()
        copy_data['sequences'] = [{key: value for key, value in result['items'][1].items() if key not in ('id', 'animation')}]
        copy_data['sequences'][0]['titre'] = 'Copie modifiée'
        created = self.mutate('post', '/api/animations', copy_data)
        self.assertEqual(created.status_code, 201, created.json)
        self.assertNotIn(created.json['sequences'][0]['id'], [s['id'] for s in result['items']])
        self.assertEqual(self.client.get(f"/api/animations/{other['id']}").json['sequences'][0]['titre'], 'Jeu du castor')
        self.assertEqual(self.client.get('/api/sequences').json['total'], 3)
        # Une copie non modifiée n'apparaît pas une seconde fois dans la liste.
        same = self.animation_data()
        same['sequences'] = [{key: value for key, value in result['items'][1].items() if key not in ('id', 'animation')}]
        self.assertEqual(self.mutate('post', '/api/animations', same).status_code, 201)
        self.assertEqual(self.client.get('/api/sequences').json['total'], 3)
        # Les séquences d'animations privées restent invisibles aux autres utilisateurs.
        self.login('bob')
        self.assertEqual(self.client.get('/api/sequences').json['total'], 0)

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
        response = self.mutate('post', '/api/media', content_type='multipart/form-data',
                               data={'data': json.dumps(self.material_data()), 'file': (io.BytesIO(b'%PDF test'), '../../test.pdf')})
        self.assertEqual(response.status_code, 201, response.json)
        key = response.json['id']
        self.assertNotIn('url', response.json)
        response = self.client.get(f'/api/media/{key}/file')
        self.assertEqual(response.data, b'%PDF test')
        response.close()
        self.assertEqual(self.client.get('/api/media?tag=5').json['total'], 1)
        nom = self.material_data()['nom']
        self.assertEqual(self.client.get(f'/api/media?q={nom[:3].upper()}').json['total'], 1)
        self.assertEqual(self.client.get('/api/media?q=%25zzz_').json['total'], 0)
        neighbors = self.client.get(f'/api/media/{key}/neighbors').json
        self.assertEqual((neighbors['found'], neighbors['previous'], neighbors['next'], neighbors['total']), (True, None, None, 1))
        self.assertFalse(self.client.get(f'/api/media/{key}/neighbors?q=%25zzz_').json['found'])
        self.assertEqual(self.mutate('delete', f'/api/media/{key}').status_code, 403)
        response = self.client.get(f'/api/media/{key}/download')
        with ZipFile(io.BytesIO(response.data)) as archive:
            self.assertTrue(any(name.endswith('.odt') for name in archive.namelist()))
            self.assertTrue(any(name.startswith('medias/') for name in archive.namelist()))
        self.login('admin')
        self.assertEqual(self.mutate('delete', f'/api/media/{key}').status_code, 204)
        self.assertTrue(list(Path(self.settings['paths']['uploads']).glob('*.pdf')))

    def test_upload_too_large_has_french_message(self):
        self.login('admin')
        self.app.config['MAX_CONTENT_LENGTH'] = 1024 * 1024
        response = self.mutate('post', '/api/media', data={'data': '{}', 'file': (io.BytesIO(b'x' * 2 * 1024 * 1024), 'a.mp4')},
                               content_type='multipart/form-data')
        self.assertEqual(response.status_code, 413)
        self.assertIn('limite : 1 Mo', response.json['error']['message'])

    def test_files_config_lists_allowed_extensions(self):
        response = self.client.get('/api/files/config')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json['allowed_extensions'], sorted(self.settings['backend']['allowed_extensions']))

    def test_outil_facilitateur_crud_and_separation(self):
        data = {'nom': 'Un outil', 'fk_type_outil_id': 7, 'difficulte_id': 8, 'variante': '<p>v</p>', 'materiel': '<p>m</p>'}
        response = self.mutate('post', '/api/outils', data)
        self.assertEqual(response.status_code, 201, response.json)
        key = response.json['id']
        self.assertEqual(response.json['difficulte_id'], 8)
        self.assertNotIn('localisation', response.json)
        # Un type de média n'est pas un type d'outil, et inversement.
        self.assertEqual(self.mutate('post', '/api/outils', {**data, 'fk_type_outil_id': 6}).status_code, 422)
        self.assertEqual(self.mutate('post', '/api/media', {'nom': 'x', 'fk_type_mat_id': 7}).status_code, 422)
        self.assertEqual(self.client.get('/api/outils?q=outil').json['total'], 1)
        self.assertEqual(self.client.get('/api/outils?difficulte=8').json['total'], 1)
        self.assertEqual(self.client.get('/api/outils?difficulte=1').json['total'], 0)
        self.assertEqual(self.client.get('/api/media?q=outil').json['total'], 0)
        self.assertEqual(self.client.get(f'/api/outils/{key}').json['nom'], 'Un outil')
        self.assertEqual(self.client.get(f'/api/media/{key}').status_code, 404)
        response = self.client.get(f'/api/outils/{key}/download')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.mutate('delete', f'/api/outils/{key}').status_code, 403)
        self.login('admin')
        self.mutate('put', '/api/pages/briseglace', {'contenu': 'Page'})
        self.assertEqual(self.client.get('/api/pages/briseglace').json['documents'][0]['id'], key)
        self.assertEqual(self.mutate('put', f'/api/outils/{key}', {**data, 'nom': 'Renommé'}).json['nom'], 'Renommé')
        self.assertEqual(self.mutate('delete', f'/api/outils/{key}').status_code, 204)
        self.assertEqual(self.client.get(f'/api/outils/{key}').status_code, 404)

    def test_taxhub_search_media_and_import(self):
        from animmalle import taxhub
        medias = [{'id_media': 5, 'titre': 'Salamandre', 'auteur': 'A', 'source': 'PNC', 'id_type': 2,
                   'media_url': 'https://taxhub.test/static/medias/92 Salamandre.jpg'}]
        taxa = [{'cd_ref': 92, 'lb_nom': 'Salamandra salamandra', 'nom_vern': 'Salamandre', 'search_name': 'x'},
                {'cd_ref': 93, 'lb_nom': 'Sans media', 'nom_vern': None}]
        taxhub._NO_MEDIA.clear()
        def fake(url, limit):
            if 'allnamebylist' in url:
                return json.dumps(taxa).encode()
            if 'bycdref/93' in url:
                return b'[]'
            if 'bycdref/92' in url:
                return json.dumps(medias).encode()
            self.assertEqual(url, 'https://taxhub.test/static/medias/92%20Salamandre.jpg')
            return b'\xff\xd8 image'
        with patch.object(taxhub, '_get', fake):
            self.assertEqual([item['cd_ref'] for item in self.client.get('/api/taxhub/taxa?q=sala').json['items']], [92])
            self.assertEqual(self.client.get('/api/taxhub/taxa?q=sa').json['items'], [])
            with self.db() as db:
                self.assertEqual(list(db.scalars(select(TaxonMedia.cd_ref))), [92])
            # Un taxon déjà enregistré n'est plus revérifié, même si TaxHub ne publie plus son média.
            medias.clear()
            taxhub._NO_MEDIA.clear()
            self.assertEqual([item['cd_ref'] for item in self.client.get('/api/taxhub/taxa?q=sala').json['items']], [92])
            medias.append({'id_media': 5, 'titre': 'Salamandre', 'auteur': 'A', 'source': 'PNC', 'id_type': 2,
                           'media_url': 'https://taxhub.test/static/medias/92 Salamandre.jpg'})
            self.assertEqual(self.client.get('/api/taxhub/taxa/92/media').json['items'][0]['id_media'], 5)
            self.assertEqual(self.mutate('post', '/api/taxhub/import', {'cd_ref': 92, 'id_media': 6, 'fk_type_mat_id': 6}).status_code, 404)
            self.assertEqual(self.mutate('post', '/api/taxhub/import', {'cd_ref': 92, 'id_media': 5}).status_code, 422)
            response = self.mutate('post', '/api/taxhub/import', {'cd_ref': 92, 'id_media': 5, 'fk_type_mat_id': 6})
            self.assertEqual(response.status_code, 201, response.json)
            self.assertEqual(response.json['nom'], 'Salamandre')
            self.assertEqual(response.json['extension'], 'jpg')

    def test_taxhub_sort_by_vernacular_name(self):
        from animmalle import taxhub
        items = [{'lb_nom': 'Zus', 'nom_vern': None}, {'lb_nom': 'Vulpina sp', 'nom_vern': None},
                 {'lb_nom': 'A', 'nom_vern': 'Laîche des renards'}, {'lb_nom': 'B', 'nom_vern': 'Renard roux, Goupil'},
                 {'lb_nom': 'C', 'nom_vern': "Vulpie queue-d'écureuil"}, {'lb_nom': 'D', 'nom_vern': 'Vigne des Vulpins'},
                 {'lb_nom': 'E', 'nom_vern': 'Vulpie queue-de-rat'}]
        ranked = sorted(items, key=lambda item: taxhub._sort_key(item, 'vulp'))
        self.assertEqual([item['lb_nom'] for item in ranked], ['C', 'E', 'D', 'A', 'B', 'Vulpina sp', 'Zus'])

    def test_material_thumbnail(self):
        from PIL import Image
        picture = io.BytesIO()
        Image.new('RGBA', (2000, 1000), (255, 0, 0, 128)).save(picture, 'PNG')
        result = self.mutate('post', '/api/media', content_type='multipart/form-data',
                             data={'data': json.dumps(self.material_data()),
                                   'file': (io.BytesIO(picture.getvalue()), 'grande.png')})
        key = result.json['id']
        response = self.client.get(f'/api/media/{key}/thumbnail')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, 'image/jpeg')
        self.assertIn('max-age', response.headers['Cache-Control'])
        with Image.open(io.BytesIO(response.data)) as thumbnail:
            self.assertLessEqual(thumbnail.width, 480)
            self.assertLess(len(response.data), len(picture.getvalue()) + 5000)
        response.close()
        self.assertEqual(self.client.get('/api/media/999999/thumbnail').status_code, 404)
        self.login('admin')
        self.mutate('post', f'/api/media/{key}/file', data={'file': (io.BytesIO(b'zip'), 'archive.zip')})
        self.assertEqual(self.client.get(f'/api/media/{key}/thumbnail').status_code, 415)
        self.assertEqual(self.client.get(f'/api/media/{key}').json['extension'], 'zip')
        page = io.BytesIO()
        Image.new('RGB', (600, 800), 'white').save(page, 'PDF')
        self.mutate('post', f'/api/media/{key}/file', data={'file': (io.BytesIO(page.getvalue()), 'page.pdf')})
        if shutil.which('pdftoppm'):
            response = self.client.get(f'/api/media/{key}/thumbnail')
            self.assertEqual(response.status_code, 200)
            with Image.open(io.BytesIO(response.data)) as thumbnail:
                self.assertEqual(thumbnail.width, 480)
            response.close()
        self.mutate('post', f'/api/media/{key}/file', data={'file': (io.BytesIO(b'%PDF casse'), 'casse.pdf')})
        with patch('animmalle.files.shutil.which', return_value=None):
            self.assertEqual(self.client.get(f'/api/media/{key}/thumbnail').status_code, 503)
        self.mutate('post', f'/api/media/{key}/file', data={'file': (io.BytesIO(b'x'), 'film.mp4')})
        with patch('animmalle.files.shutil.which', return_value=None):
            self.assertEqual(self.client.get(f'/api/media/{key}/thumbnail').status_code, 503)
        with patch('animmalle.files.shutil.which', return_value='/usr/bin/ffmpeg'):
            with patch('animmalle.files.subprocess.run', side_effect=subprocess.CalledProcessError(1, 'ffmpeg')):
                self.assertEqual(self.client.get(f'/api/media/{key}/thumbnail').status_code, 422)

    def test_presentation_thumbnail(self):
        from PIL import Image
        result = self.mutate('post', '/api/media', content_type='multipart/form-data',
                             data={'data': json.dumps(self.material_data()),
                                   'file': (io.BytesIO(b'pptx'), 'cours.pptx')})
        key = result.json['id']
        self.assertEqual(self.client.get(f'/api/media/{key}').json['extension'], 'pptx')
        calls = []

        def fake_run(command, **kwargs):
            calls.append(command[0])
            if command[0].endswith(('libreoffice', 'soffice')):
                Image.new('RGB', (10, 10)).save(Path(command[command.index('--outdir') + 1]) / (Path(command[-1]).stem + '.pdf'))
            else:
                Image.new('RGB', (800, 450), 'white').save(command[-1] + '.jpg')
        with patch('animmalle.files.shutil.which', side_effect=lambda name: f'/usr/bin/{name}'):
            with patch('animmalle.files.subprocess.run', side_effect=fake_run):
                response = self.client.get(f'/api/media/{key}/thumbnail')
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.mimetype, 'image/jpeg')
                response.close()
                self.client.get(f'/api/media/{key}/thumbnail').close()
        self.assertEqual(len(calls), 2)  # LibreOffice puis pdftoppm, une seule fois (cache)

    def test_audio_preview_conversion(self):
        result = self.mutate('post', '/api/media', content_type='multipart/form-data',
                             data={'data': json.dumps(self.material_data()),
                                   'file': (io.BytesIO(b'wma'), 'son.wma')})
        key = result.json['id']
        with patch('animmalle.files.shutil.which', return_value='/usr/bin/ffmpeg'):
            with patch('animmalle.files.subprocess.Popen') as popen:
                def convert(command, **kwargs):
                    self.assertIn('-vn', command[2])
                    Path(command[-1]).write_bytes(b'm4a converti')
                    return MagicMock(wait=MagicMock(return_value=0))
                popen.side_effect = convert
                response = self.client.get(f'/api/media/{key}/preview')
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.mimetype, 'audio/mp4')
                self.assertEqual(response.data, b'm4a converti')
                response.close()

    def test_video_preview_conversion(self):
        result = self.mutate('post', '/api/media', content_type='multipart/form-data',
                             data={'data': json.dumps(self.material_data()),
                                   'file': (io.BytesIO(b'avi'), 'film.avi')})
        key = result.json['id']
        with patch('animmalle.files.shutil.which', return_value=None):
            self.assertEqual(self.client.get(f'/api/media/{key}/preview').status_code, 503)
        with patch('animmalle.files.shutil.which', return_value='/usr/bin/ffmpeg'):
            with patch('animmalle.files.subprocess.Popen') as popen:
                def convert(command, **kwargs):
                    Path(command[-1]).write_bytes(b'mp4 converti')
                    return MagicMock(wait=MagicMock(return_value=0))
                popen.side_effect = convert
                response = self.client.get(f'/api/media/{key}/preview')
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.mimetype, 'video/mp4')
                self.assertEqual(response.data, b'mp4 converti')
                response.close()
                self.assertEqual(popen.call_count, 1)
                self.client.get(f'/api/media/{key}/preview').close()
                self.assertEqual(popen.call_count, 1)  # servi depuis le cache
        self.login('admin')
        self.mutate('post', f'/api/media/{key}/file', data={'file': (io.BytesIO(b'avi2'), 'autre.avi')})
        with patch('animmalle.files.shutil.which', return_value='/usr/bin/ffmpeg'):
            with patch('animmalle.files.subprocess.Popen') as popen:
                popen.return_value = MagicMock(wait=MagicMock(side_effect=subprocess.TimeoutExpired('ffmpeg', 40)))
                self.assertEqual(self.client.get(f'/api/media/{key}/preview').status_code, 503)

    def test_material_preview(self):
        result = self.mutate('post', '/api/media', content_type='multipart/form-data',
                             data={'data': json.dumps(self.material_data()),
                                   'file': (io.BytesIO(b'%PDF test'), 'test.pdf')})
        key = result.json['id']
        response = self.client.get(f'/api/media/{key}/preview')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, 'application/pdf')
        self.assertEqual(response.data, b'%PDF test')
        self.assertEqual(response.headers['Cache-Control'], 'no-store')
        response.close()
        self.login('admin')
        self.mutate('post', f'/api/media/{key}/file',
                    data={'file': (io.BytesIO(b'office'), 'test.odt')})
        with patch('animmalle.files.shutil.which', return_value=None):
            self.assertEqual(self.client.get(f'/api/media/{key}/preview').status_code, 503)
        with patch('animmalle.files.shutil.which', return_value='/usr/bin/libreoffice'):
            with patch('animmalle.files.subprocess.run') as convert:
                def produce(command, **kwargs):
                    output = Path(command[command.index('--outdir') + 1])
                    (output / (Path(command[-1]).stem + '.pdf')).write_bytes(b'%PDF converted')
                convert.side_effect = produce
                response = self.client.get(f'/api/media/{key}/preview')
                self.assertEqual(response.data, b'%PDF converted')
                response.close()
            with patch('animmalle.files.subprocess.run'):
                self.assertEqual(self.client.get(f'/api/media/{key}/preview').status_code, 422)
        self.assertEqual(self.client.get('/api/media/999999/preview').status_code, 404)

    def test_material_relations_and_invalid_upload(self):
        result = self.mutate('post', '/api/media', self.material_data())
        key = result.json['id']
        data = self.animation_data()
        data['sequences'][0]['materiel'] = [key]
        anim = self.mutate('post', '/api/animations', data).json
        self.login('admin')
        response = self.mutate('post', f'/api/media/{key}/file',
                               data={'file': (io.BytesIO(b'bad'), 'test.exe')})
        self.assertEqual(response.status_code, 422)
        self.assertEqual(self.mutate('delete', f'/api/media/{key}').status_code, 204)
        self.assertEqual(self.client.get(f"/api/animations/{anim['id']}").json['sequences'][0]['materiel'], [])

    def test_thesaurus_reserved_to_thesaurus_groups(self):
        auth = self.client.application.extensions['settings']['auth']
        auth['admin_groups'] = ['admin', 'autre']
        auth['thesaurus_groups'] = ['admin']
        auth['users'][2]['groups'] = ['autre']
        self.login('bob')
        self.assertTrue(self.client.get('/api/auth/session').json['is_admin'])
        self.assertFalse(self.client.get('/api/auth/session').json['can_edit_thesaurus'])
        data = {'label': 'Tag', 'reference': 'ref.thematiques'}
        self.assertEqual(self.mutate('post', '/api/thesaurus', data).status_code, 403)
        self.assertEqual(self.mutate('put', '/api/thesaurus/5', {'label': 'Autre'}).status_code, 403)
        self.assertEqual(self.mutate('delete', '/api/thesaurus/5').status_code, 403)
        self.assertEqual(self.mutate('delete', '/api/thesaurus/5/pictogram').status_code, 403)
        self.login('admin')
        self.assertTrue(self.client.get('/api/auth/session').json['can_edit_thesaurus'])
        self.assertEqual(self.mutate('post', '/api/thesaurus', data).status_code, 201)

    def test_thesaurus_duplicates_references_and_delete(self):
        self.assertEqual(self.mutate('post', '/api/thesaurus', {'label': 'Tag', 'reference': 'ref.thematiques'}).status_code, 403)
        self.login('admin')
        data = {'label': 'Tag', 'reference': 'ref.thematiques'}
        created = self.mutate('post', '/api/thesaurus', data)
        self.assertEqual(created.status_code, 201)
        self.assertEqual(self.mutate('post', '/api/thesaurus', data).status_code, 409)
        self.assertEqual(self.mutate('delete', '/api/thesaurus/105').status_code, 409)
        self.assertEqual(self.mutate('delete', f"/api/thesaurus/{created.json['id']}").status_code, 204)
        self.create_animation()
        self.assertEqual(self.mutate('delete', '/api/thesaurus/1').status_code, 409)

    def test_thesaurus_move_changes_display_order(self):
        self.login('admin')
        first = self.mutate('post', '/api/thesaurus', {'label': 'B', 'reference': 'ref.thematiques'}).json
        second = self.mutate('post', '/api/thesaurus', {'label': 'A', 'reference': 'ref.thematiques'}).json
        self.assertEqual(second['position'], first['position'] + 1)

        def order():
            items = self.client.get('/api/thesaurus?reference=ref.thematiques').json['items']
            return [item['label'] for item in items if item['label'] in ('A', 'B')]

        self.assertEqual(order(), ['B', 'A'])
        self.assertEqual(self.mutate('put', f"/api/thesaurus/{second['id']}/move", {'direction': 'up'}).status_code, 200)
        self.assertEqual(order(), ['A', 'B'])
        self.assertEqual(self.mutate('put', f"/api/thesaurus/{second['id']}/move", {'direction': 'up'}).status_code, 200)
        self.assertEqual(order(), ['A', 'B'])
        self.assertEqual(self.mutate('put', f"/api/thesaurus/{second['id']}/move", {'direction': 'x'}).status_code, 422)

    def test_pictogram_upload_replace_rename_delete(self):
        png = b'\x89PNG\r\n\x1a\n' + b'0' * 20
        def send(data, name='a.png'):
            return self.mutate('put', '/api/thesaurus/5/pictogram', content_type='multipart/form-data',
                               data={'file': (io.BytesIO(data), name)})
        self.assertEqual(send(png).status_code, 403)
        self.login('admin')
        item = next(i for i in self.client.get('/api/thesaurus').json['items'] if i['id'] == 5)
        self.assertEqual(item['reference'], 'ref.thematiques')
        self.assertEqual(self.client.get('/api/thesaurus/5/pictogram').status_code, 404)
        self.assertEqual(send(b'pas un png').status_code, 422)
        self.assertEqual(send(png).status_code, 204)
        self.assertEqual(self.client.get('/api/thesaurus/5/pictogram').data, png)
        self.assertEqual(send(png + b'1').status_code, 204)
        self.assertEqual(self.client.get('/api/thesaurus/5/pictogram').data, png + b'1')
        self.assertEqual(self.mutate('put', '/api/thesaurus/5', {'label': 'Nouveau nom'}).status_code, 200)
        self.assertEqual(self.client.get('/api/thesaurus/5/pictogram').data, png + b'1')
        self.assertEqual(self.mutate('delete', '/api/thesaurus/5/pictogram').status_code, 204)
        self.assertEqual(self.mutate('delete', '/api/thesaurus/5/pictogram').status_code, 404)
        self.assertEqual(send(png).status_code, 204)
        self.assertEqual(self.mutate('put', '/api/thesaurus/5', {'label': 'a/b'}).status_code, 200)
        self.assertEqual(send(png).status_code, 422)
        self.assertEqual(self.mutate('put', '/api/thesaurus/1/pictogram', content_type='multipart/form-data',
                                     data={'file': (io.BytesIO(png), 'a.png')}).status_code, 204)

    def test_thesaurus_update_label(self):
        path = '/api/thesaurus/1'
        self.assertEqual(self.mutate('put', path, {'label': 'Renommé'}).status_code, 403)
        self.login('admin')
        before = next(item for item in self.client.get('/api/thesaurus').json['items'] if item['id'] == 1)
        response = self.mutate('put', path, {'label': 'Renommé'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json, {**before, 'label': 'Renommé'})
        self.assertEqual(self.mutate('put', path, {'label': ''}).status_code, 422)
        self.assertEqual(self.mutate('put', path, {'label': 'x' * 81}).status_code, 422)
        self.assertEqual(self.mutate('put', path, {'label': 'Renommé', 'code': 'changed'}).status_code, 422)
        self.assertEqual(self.mutate('put', '/api/thesaurus/99999', {'label': 'Absent'}).status_code, 404)
        duplicate = self.mutate('post', '/api/thesaurus', {'label': 'Autre entrée', 'reference': 'ref.thematiques'})
        self.assertEqual(duplicate.status_code, 201)
        self.assertEqual(self.mutate('put', path, {'label': 'Autre entrée'}).status_code, 409)

    def test_pages_revisions_and_sanitization(self):
        directory = Path(self.settings['paths']['pages']) / 'notice'
        directory.mkdir(parents=True)
        (directory / 'current.md').write_text('Ancienne notice')
        self.assertEqual(self.client.get('/api/pages/notice').json['contenu'], 'Ancienne notice')
        self.assertEqual(self.mutate('put', '/api/pages/notice', {'contenu': 'Test'}).status_code, 403)
        self.login('admin')
        response = self.mutate('put', '/api/pages/notice', {'contenu': '# Nouveau\n<script>alert(1)</script>[clic](javascript:alert(1))'})
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('<script', response.json['html'])
        self.assertNotIn('javascript:', response.json['html'])
        self.assertEqual((directory / 'current.md').read_text(), response.json['contenu'])
        revision = next(directory.glob('rev_*.md'))
        self.assertEqual(revision.read_text(), 'Ancienne notice')
        self.assertEqual(len(list((Path(self.settings['paths']['pages']) / 'notice').glob('rev_*.md'))), 1)
        self.assertEqual(self.client.get('/api/pages/bad.name').status_code, 404)

    def test_export_missing_files_and_odt_xml(self):
        from animmalle.models import Media
        material = self.mutate('post', '/api/media', self.material_data()).json
        with self.db() as db:
            db.get(Media, material['id']).url = '/outside/nonexistent.pdf'
            db.commit()
        data = self.animation_data()
        data['sequences'][0]['materiel'] = [material['id']]
        item = self.mutate('post', '/api/animations', data).json
        response = self.client.get(f"/api/animations/{item['id']}/download")
        from xml.etree import ElementTree
        with ZipFile(io.BytesIO(response.data)) as archive:
            names = archive.namelist()
            self.assertFalse([name for name in names if name.endswith('.json')])
            odt = next(name for name in names if name.endswith('.odt'))
            with ZipFile(io.BytesIO(archive.read(odt))) as document:
                ElementTree.fromstring(document.read('content.xml'))
                ElementTree.fromstring(document.read('styles.xml'))
                self.assertEqual(document.infolist()[0].filename, 'mimetype')
                self.assertEqual(document.infolist()[0].compress_type, 0)

    def test_export_includes_outils_in_sequences(self):
        outil = self.mutate('post', '/api/outils', {'nom': 'Un outil <b>', 'fk_type_outil_id': 7, 'difficulte_id': 8,
                                                  'description': '<p>desc</p>', 'variante': '<p>une variante</p>',
                                                  'materiel': '<p>du matériel</p>'}).json
        data = self.animation_data()
        data['sequences'][0]['outils'] = [outil['id']]
        item = self.mutate('post', '/api/animations', data).json
        response = self.client.get(f"/api/animations/{item['id']}/download")
        from xml.etree import ElementTree
        with ZipFile(io.BytesIO(response.data)) as archive:
            odt = next(name for name in archive.namelist() if name.endswith('.odt'))
            with ZipFile(io.BytesIO(archive.read(odt))) as document:
                content = document.read('content.xml').decode()
        ElementTree.fromstring(content)
        for text in ('OUTIL FACILITATEUR', 'Un outil &lt;b&gt;', 'VARIANTE', 'une variante', 'MATÉRIEL', 'du matériel'):
            self.assertIn(text, content)

    def test_animation_neighbors(self):
        first = self.create_animation()
        data = self.animation_data()
        data['titre'] = 'Zèbre'
        second = self.mutate('post', '/api/animations', data).json
        ids = [first['id'], second['id']]
        titles = {first['id']: self.animation_data()['titre'], second['id']: 'Zèbre'}
        order = sorted(ids, key=lambda key: titles[key])
        result = self.client.get(f'/api/animations/{order[0]}/neighbors').json
        self.assertTrue(result['found'])
        self.assertIsNone(result['previous'])
        self.assertEqual(result['next']['id'], order[1])
        self.assertEqual((result['position'], result['total']), (1, 2))
        result = self.client.get(f'/api/animations/{order[1]}/neighbors').json
        self.assertEqual(result['previous']['id'], order[0])
        self.assertIsNone(result['next'])
        filtered = self.client.get(f'/api/animations/{order[0]}/neighbors?q=Zèbre').json
        self.assertFalse(filtered['found'])
        self.assertEqual(self.client.get('/api/animations/inconnue/neighbors').json['found'], False)

    def test_search_stats_authors_errors(self):
        self.create_animation()
        response = self.client.get('/api/animations?tag=5&page_size=1')
        self.assertEqual(response.json['items'][0]['pertinence']['matched'], 1)
        self.assertEqual(response.json['items'][0]['duree_minutes'], 10)
        self.assertEqual((response.json['duree_min'], response.json['duree_max']), (10, 10))
        self.assertEqual(response.json['items'][0]['fk_duree_id'], 1)
        self.assertEqual(self.client.get('/api/animations?tag=999').json['total'], 0)
        for query, total in (('duree_min=10&duree_max=10', 1), ('duree_min=5&duree_max=15', 1), ('duree_min=11', 0),
                             ('duree_max=9', 0), ('duree_min=0', 1)):
            self.assertEqual(self.client.get(f'/api/animations?{query}').json['total'], total, query)
        self.assertEqual(self.client.get('/api/animations?duree_min=x').status_code, 422)
        self.assertEqual(self.client.get('/api/animations?page_size=0').status_code, 422)
        self.assertEqual(self.client.get('/api/media?type=no').status_code, 422)
        self.assertEqual(self.client.get('/api/stats').status_code, 200)
        self.assertEqual(self.client.get('/api/authors?q=ali').json['items'], ['alice'])
        self.assertEqual(self.client.get('/api/media/999').status_code, 404)
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

    def test_ldap_without_tls_authentication_and_directory(self):
        from animmalle.auth import authenticate, directory_users
        config = yaml.safe_load((ROOT / 'installation/config_principal.example.yaml').read_text())['auth']
        config['ldap'].update(ssl=False, start_tls=False, port=389,
                              service_bind_dn='reader', service_password='test')
        self.app.extensions['settings']['auth'] = config
        entry = MagicMock()
        entry.entry_attributes_as_dict = {'cn': ['Alice'], 'memberOf': []}
        entry.__getitem__.return_value = 'Alice'
        with self.app.app_context(), patch('ldap3.Connection') as factory, patch('ldap3.Server') as server, patch('ldap3.Tls') as tls:
            connection = factory.return_value
            connection.bind.return_value = True
            connection.search.return_value = True
            connection.entries = [entry]
            self.assertEqual(authenticate('alice', 'test'), {'name': 'Alice', 'groups': []})
            self.assertEqual(directory_users('al'), ['Alice'])
            connection.start_tls.assert_not_called()
            tls.assert_not_called()
            self.assertEqual(connection.bind.call_count, 2)
            for call in server.call_args_list:
                self.assertFalse(call.kwargs['use_ssl'])
                self.assertIsNone(call.kwargs['tls'])

    def test_ldap_start_tls_configuration_validation(self):
        settings = copy.deepcopy(self.settings)
        settings['auth'] = yaml.safe_load((ROOT / 'installation/config_principal.example.yaml').read_text())['auth']
        for value in (True, False):
            settings['auth']['ldap']['start_tls'] = value
            self.config_path.write_text(yaml.safe_dump(settings))
            self.assertIs(load_settings(self.config_path)['auth']['ldap']['start_tls'], value)
        settings['auth']['ldap']['start_tls'] = 'false'
        self.config_path.write_text(yaml.safe_dump(settings))
        with self.assertRaisesRegex(ValueError, 'start_tls'):
            load_settings(self.config_path)
        del settings['auth']['ldap']['start_tls']
        self.config_path.write_text(yaml.safe_dump(settings))
        load_settings(self.config_path)

    def test_ldap_tls_failure_survives_unbind_failure(self):
        import ldap3
        from werkzeug.exceptions import ServiceUnavailable
        from animmalle.auth import authenticate, directory_users
        config = yaml.safe_load((ROOT / 'installation/config_principal.example.yaml').read_text())['auth']
        config['ldap'].update(ssl=False, service_bind_dn='reader', service_password='test')
        self.app.extensions['settings']['auth'] = config
        with self.app.app_context(), patch('ldap3.Connection') as factory:
            connection = factory.return_value
            connection.start_tls.side_effect = ldap3.core.exceptions.LDAPStartTLSError('certificate failure')
            connection.unbind.side_effect = ldap3.core.exceptions.LDAPSocketSendError('socket closed')
            for operation in (lambda: authenticate('alice', 'test'), lambda: directory_users('al')):
                with self.assertRaises(ServiceUnavailable):
                    operation()
            connection.bind.assert_not_called()

    def test_ldap_custom_ca_preserves_certificate_validation(self):
        import ssl
        from animmalle.auth import directory_tls
        with patch('ldap3.Tls') as tls:
            directory_tls({'ca_certs_file': '/test/authority.pem'})
            tls.assert_called_once_with(validate=ssl.CERT_REQUIRED, ca_certs_file='/test/authority.pem')

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
