"""Parcours de install.sh avec sudo/Python simulés : aucune commande privilégiée ni accès à la base."""

import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

FAKE_PYTHON = '''#!/bin/sh
printf "python %s\\n" "$*" >> "$INSTALL_TEST_LOG"
case "$*" in
  *check.py*) [ "$INSTALL_TEST_CHECK_STATUS" = 0 ] || { echo "Configuration invalide : test" >&2; exit 1; }
              echo "PG_LOCAL=$INSTALL_TEST_PG_LOCAL"; echo "PG_PORT=5432" ;;
esac
'''


@unittest.skipIf(os.geteuid() == 0, 'Le script refuse le compte root.')
class InstallTests(unittest.TestCase):
    def run_phase(self, phase, sudo_status=0, pg_local=1, check_status=0, config_mode=0o600, config=True):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            installation = root / 'installation'
            installation.mkdir()
            script = installation / 'install.sh'
            shutil.copyfile(Path(__file__).resolve().parents[1] / 'install.sh', script)
            if config:
                yaml = installation / 'config_principal.yaml'
                yaml.write_text('postgresql: {}\n')
                yaml.chmod(config_mode)
            binaries = root / 'bin'
            binaries.mkdir()
            log = root / 'calls'
            sudo = binaries / 'sudo'
            sudo.write_text('#!/bin/sh\nprintf "sudo %s\\n" "$*" >> "$INSTALL_TEST_LOG"\nexit "$INSTALL_TEST_SUDO_STATUS"\n')
            sudo.chmod(0o700)
            venv = root / '.venv/bin'
            venv.mkdir(parents=True)
            python = venv / 'python'
            python.write_text(FAKE_PYTHON)
            python.chmod(0o700)
            env = dict(os.environ, PATH=f'{binaries}:{os.environ["PATH"]}',
                       INSTALL_TEST_LOG=str(log), INSTALL_TEST_SUDO_STATUS=str(sudo_status),
                       INSTALL_TEST_PG_LOCAL=str(pg_local), INSTALL_TEST_CHECK_STATUS=str(check_status))
            env.pop('INSTALL_LOG', None)
            result = subprocess.run(['bash', str(script), phase], env=env, capture_output=True, text=True)
            calls = log.read_text().splitlines() if log.exists() else []
            # L'import de contrôle du venv n'intéresse pas l'ordre des opérations.
            calls = [c for c in calls if not c.startswith('python -c')]
            logs = list((installation / 'logs').glob('install-*.log')) if (installation / 'logs').exists() else []
            return result, calls, logs

    def test_schema_validates_config_then_authenticates(self):
        result, calls, logs = self.run_phase('schema')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue(calls[0].endswith('check.py database'))
        self.assertTrue(calls[1].startswith('sudo '))
        self.assertTrue(calls[-1].endswith('database.py schema'))
        self.assertEqual(len(logs), 1)

    def test_remote_postgres_schema_needs_no_sudo(self):
        result, calls, _ = self.run_phase('schema', pg_local=0)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertFalse(any(c.startswith('sudo') for c in calls))

    def test_failed_authentication_stops_schema(self):
        result, calls, _ = self.run_phase('schema', sudo_status=1)
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(any('database.py' in c for c in calls))

    def test_invalid_config_stops_before_sudo(self):
        result, calls, _ = self.run_phase('schema', check_status=1)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Configuration invalide', result.stdout + result.stderr)
        self.assertFalse(any(c.startswith('sudo') for c in calls))

    def test_unprotected_config_is_refused(self):
        result, calls, _ = self.run_phase('restore', config_mode=0o644)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('chmod 600', result.stdout + result.stderr)
        self.assertEqual(calls, [])

    def test_missing_config_is_reported(self):
        result, calls, _ = self.run_phase('schema', config=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('config_principal.example.yaml', result.stdout + result.stderr)

    def test_restore_does_not_request_sudo(self):
        result, calls, _ = self.run_phase('restore')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertFalse(any(c.startswith('sudo') for c in calls))
        self.assertTrue(calls[-1].endswith('database.py restore'))

    def test_unknown_phase_shows_usage(self):
        result, calls, _ = self.run_phase('inconnue')
        self.assertEqual(result.returncode, 2)
        self.assertIn('Usage', result.stdout)
        self.assertEqual(calls, [])


if __name__ == '__main__':
    unittest.main()
