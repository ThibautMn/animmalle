"""Vérifications sans serveur et sans création de base."""

import importlib.util
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from alembic import command
from alembic.config import Config
from sqlalchemy import MetaData, Table
from sqlalchemy.schema import CreateTable, conv
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import configure_mappers

from animmalle.config import CONFIG_PATH, load_database_url
from animmalle.models import APPLICATION_TABLES, Animation, Base, Commentaire, Media, OutilFacilitateur

BACKEND = Path(__file__).resolve().parents[1]


class SchemaTests(unittest.TestCase):
    def test_relationships_and_historical_nullability(self):
        configure_mappers()
        self.assertEqual(len(Base.metadata.tables), 13)
        self.assertTrue(OutilFacilitateur.__table__.c.difficulte_id.nullable)
        for name in ('localisation', 'variante', 'difficulte_id', 'materiel', 'fk_type_mat_outil_id'):
            self.assertNotIn(name, Media.__table__.c)
        self.assertFalse(Commentaire.__table__.c.fk_id_anim_id.nullable)
        self.assertTrue(Animation.sequences.property.viewonly)
        self.assertEqual(Animation.commentaires.property.back_populates, 'fk_id_anim')
        self.assertEqual(str(Animation.__table__.c.date_modif.server_default.arg), 'CURRENT_DATE')

    def test_frozen_migration_matches_models(self):
        spec = importlib.util.spec_from_file_location(
            'initial', BACKEND / 'migrations/versions/0001_initial.py')
        migration = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(migration)
        metadata = MetaData()
        indexes = []
        def create_table(name, *items, **kwargs):
            Table(name, metadata, *items, **kwargs)
        with patch.object(migration.op, 'f', side_effect=conv), \
                patch.object(migration.op, 'create_table', side_effect=create_table), \
                patch.object(migration.op, 'create_index', side_effect=lambda *a, **k: indexes.append(a)):
            migration.upgrade()
        self.apply_duration_migration(metadata, indexes)
        self.apply_position_migration(metadata)
        self.apply_media_migration(metadata, indexes)
        dialect = postgresql.dialect()
        self.assertEqual(set(metadata.tables), set(Base.metadata.tables) - APPLICATION_TABLES)
        for name, table in Base.metadata.tables.items():
            if name in APPLICATION_TABLES:
                continue
            self.assertEqual(sorted(line.strip().rstrip(',') for line in str(CreateTable(table).compile(dialect=dialect)).splitlines()),
                             sorted(line.strip().rstrip(',') for line in str(CreateTable(metadata.tables[name]).compile(dialect=dialect)).splitlines()))
        expected = {(i.name, t.name, tuple(c.name for c in i.columns))
                    for t in Base.metadata.tables.values() if t.name not in APPLICATION_TABLES for i in t.indexes}
        self.assertEqual(expected, {(str(a[0]), a[1], tuple(a[2])) for a in indexes})

    def apply_duration_migration(self, metadata, indexes):
        """Rejoue la migration 0004 sur le schéma gelé de 0001 pour le comparer aux modèles."""
        spec = importlib.util.spec_from_file_location(
            'duree', BACKEND / 'migrations/versions/0004_duree_sequence_minutes.py')
        migration = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(migration)
        table = metadata.tables['sequence']
        def alter_column(_table, name, **kwargs):
            table.c[name].nullable = kwargs['nullable']
        def drop_index(name, **kwargs):
            indexes[:] = [item for item in indexes if str(item[0]) != name]
        def drop_constraint(name, *args, **kwargs):
            table.constraints.discard(next(c for c in table.constraints if c.name == name))
        def drop_column(_table, name):
            table._columns.remove(table.c[name])
        with patch.object(migration.op, 'add_column', side_effect=lambda _t, column: table.append_column(column)), \
                patch.object(migration.op, 'get_bind', return_value=Mock(dialect=Mock())), \
                patch.object(migration.op, 'execute'), \
                patch.object(migration.op, 'alter_column', side_effect=alter_column), \
                patch.object(migration.op, 'drop_index', side_effect=drop_index), \
                patch.object(migration.op, 'drop_constraint', side_effect=drop_constraint), \
                patch.object(migration.op, 'drop_column', side_effect=drop_column):
            migration.upgrade()

    def apply_position_migration(self, metadata):
        """Rejoue la migration 0007 (position des termes du thésaurus)."""
        spec = importlib.util.spec_from_file_location(
            'position', BACKEND / 'migrations/versions/0007_position_thesaurus.py')
        migration = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(migration)
        table = metadata.tables['thesaurus']
        with patch.object(migration.op, 'add_column', side_effect=lambda _t, column: table.append_column(column)), \
                patch.object(migration.op, 'execute'):
            migration.upgrade()

    def apply_media_migration(self, metadata, indexes):
        """Rejoue la migration 0008 (séparation de mat_peda en media et outil_facilitateur)."""
        spec = importlib.util.spec_from_file_location(
            'media', BACKEND / 'migrations/versions/0008_separation_media_outil.py')
        migration = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(migration)
        def create_table(name, *items, **kwargs):
            Table(name, metadata, *items, **kwargs)
        def drop_table(name):
            metadata.remove(metadata.tables[name])
            indexes[:] = [item for item in indexes if item[1] != name]
        with patch.object(migration.op, 'f', side_effect=conv), \
                patch.object(migration.op, 'create_table', side_effect=create_table), \
                patch.object(migration.op, 'create_index', side_effect=lambda *a, **k: indexes.append(a)), \
                patch.object(migration.op, 'drop_table', side_effect=drop_table), \
                patch.object(migration.op, 'execute'):
            migration.upgrade()

    def test_offline_upgrade_and_downgrade_without_configuration(self):
        output = io.StringIO()
        config = Config(str(BACKEND / 'alembic.ini'), output_buffer=output)
        with patch('animmalle.config.load_database_url', side_effect=AssertionError('Connexion interdite')):
            command.upgrade(config, 'head', sql=True)
            command.downgrade(config, '0003_taxon_media:base', sql=True)
        sql = output.getvalue()
        self.assertEqual(sql.count('CREATE TABLE '), 17)
        self.assertEqual(sql.count('DROP TABLE '), 13)
        self.assertEqual(sql.count(' SERIAL '), 15)
        self.assertNotIn('datetime(', sql)
        self.assertIn('DEFAULT CURRENT_DATE', sql)
        self.assertIn('UNIQUE (fk_anim_id, fk_sequence_id)', sql)
        self.assertLess(sql.index('DROP TABLE commentaire'), sql.index('DROP TABLE animation'))

    def test_yaml_validation_and_secret_encoding(self):
        self.assertEqual(CONFIG_PATH, BACKEND.parent / 'installation/config_principal.yaml')
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'config.yaml'
            path.write_text('postgresql:\n  host: localhost\n  port: 5432\n  database: test\n  username: test\n  password: "a@b%/"\n')
            url = load_database_url(path)
            self.assertEqual(url.password, 'a@b%/')
            self.assertNotIn('a@b%/', str(url))
            path.write_text('postgresql:\n  port: true\n')
            with self.assertRaises(ValueError):
                load_database_url(path)
            path.write_text('!!python/object:builtins.object {}')
            with self.assertRaises(ValueError):
                load_database_url(path)


if __name__ == '__main__':
    unittest.main()
