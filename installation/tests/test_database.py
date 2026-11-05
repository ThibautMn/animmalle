"""Préparation du rôle local sans serveur ni commande sudo réelle."""

import importlib.util
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch

from sqlalchemy.engine import URL

SPEC = importlib.util.spec_from_file_location(
    'installation_database', Path(__file__).resolve().parents[1] / 'lib/database.py')
database = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(database)


class ProvisionTests(unittest.TestCase):
    @patch.object(database.subprocess, 'run')
    def test_secret_only_in_stdin_and_quoted(self, run):
        run.return_value = subprocess.CompletedProcess([], 0)
        password = "secret'\\avec\nretour"
        url = URL.create('postgresql+psycopg', username='anim"malle',
                         password=password, database='base"test', port=5432)
        database.provision_local_database(url)
        args, kwargs = run.call_args
        self.assertEqual(args[0][:4], ['sudo', '-u', 'postgres', 'psql'])
        self.assertNotIn(password, ' '.join(args[0]))
        self.assertIn("secret''", kwargs['input'])
        self.assertIn('WHERE NOT EXISTS (SELECT 1 FROM pg_roles', kwargs['input'])
        self.assertIn('WHERE NOT EXISTS (SELECT 1 FROM pg_database', kwargs['input'])
        self.assertNotIn('ALTER ROLE', kwargs['input'])
        self.assertNotIn('CREATEDB', kwargs['input'])
        self.assertTrue(kwargs['capture_output'])

    @patch.object(database.subprocess, 'run')
    def test_failure_hides_external_output(self, run):
        run.return_value = subprocess.CompletedProcess([], 1, stderr='secret')
        url = URL.create('postgresql+psycopg', username='animmalle',
                         password='secret', database='animmalle', port=5432)
        with self.assertRaises(ValueError) as caught:
            database.provision_local_database(url)
        self.assertNotIn('secret', str(caught.exception).replace('secrets', ''))
