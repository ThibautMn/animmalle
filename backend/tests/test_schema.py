"""Vérifications sans serveur et sans création de base."""

import importlib.util
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from alembic import command
from alembic.config import Config
from sqlalchemy import MetaData, Table
from sqlalchemy.schema import CreateTable, conv
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import configure_mappers

from animmalle.config import CONFIG_PATH, load_database_url
from animmalle.models import Animation, Base, Commentaire, MatPeda

BACKEND = Path(__file__).resolve().parents[1]


class SchemaTests(unittest.TestCase):
    def test_relationships_and_historical_nullability(self):
        configure_mappers()
        self.assertEqual(len(Base.metadata.tables), 9)
        self.assertTrue(MatPeda.__table__.c.difficulte_id.nullable)
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
        dialect = postgresql.dialect()
        self.assertEqual(set(metadata.tables), set(Base.metadata.tables))
        for name, table in Base.metadata.tables.items():
            self.assertEqual(sorted(line.strip().rstrip(',') for line in str(CreateTable(table).compile(dialect=dialect)).splitlines()),
                             sorted(line.strip().rstrip(',') for line in str(CreateTable(metadata.tables[name]).compile(dialect=dialect)).splitlines()))
        expected = {(i.name, t.name, tuple(c.name for c in i.columns))
                    for t in Base.metadata.tables.values() for i in t.indexes}
        self.assertEqual(expected, {(str(a[0]), a[1], tuple(a[2])) for a in indexes})

    def test_offline_upgrade_and_downgrade_without_configuration(self):
        output = io.StringIO()
        config = Config(str(BACKEND / 'alembic.ini'), output_buffer=output)
        with patch('animmalle.config.load_database_url', side_effect=AssertionError('Connexion interdite')):
            command.upgrade(config, 'head', sql=True)
            command.downgrade(config, '0001_initial:base', sql=True)
        sql = output.getvalue()
        self.assertEqual(sql.count('CREATE TABLE '), 10)
        self.assertEqual(sql.count('DROP TABLE '), 9)
        self.assertEqual(sql.count(' SERIAL '), 8)
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
