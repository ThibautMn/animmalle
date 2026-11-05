"""Vérifie le passage par sudo sans commande privilégiée ni accès à la base."""

import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


class InstallTests(unittest.TestCase):
    def run_phase(self, phase, sudo_status=0):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            installation = root / 'installation'
            installation.mkdir()
            script = installation / 'install.sh'
            shutil.copyfile(Path(__file__).resolve().parents[1] / 'install.sh', script)
            binaries = root / 'bin'
            binaries.mkdir()
            log = root / 'calls'
            sudo = binaries / 'sudo'
            sudo.write_text('#!/bin/sh\nprintf "sudo %s\\n" "$*" >> "$INSTALL_TEST_LOG"\nexit "$INSTALL_TEST_SUDO_STATUS"\n')
            sudo.chmod(0o700)
            venv = root / '.venv/bin'
            venv.mkdir(parents=True)
            python = venv / 'python'
            python.write_text('#!/bin/sh\nprintf "python %s\\n" "$*" >> "$INSTALL_TEST_LOG"\n')
            python.chmod(0o700)
            env = dict(os.environ, PATH=f'{binaries}:{os.environ["PATH"]}',
                       INSTALL_TEST_LOG=str(log), INSTALL_TEST_SUDO_STATUS=str(sudo_status))
            result = subprocess.run(['bash', str(script), phase], env=env,
                                    capture_output=True, text=True)
            return result, log.read_text().splitlines() if log.exists() else []

    @unittest.skipIf(os.geteuid() == 0, 'Le script refuse le compte root.')
    def test_schema_authenticates_before_python(self):
        result, calls = self.run_phase('schema')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(calls[0], 'sudo -v')
        self.assertTrue(calls[1].startswith('python '))
        self.assertTrue(calls[1].endswith('database.py schema'))

    @unittest.skipIf(os.geteuid() == 0, 'Le script refuse le compte root.')
    def test_failed_authentication_stops_schema(self):
        result, calls = self.run_phase('schema', sudo_status=1)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(calls, ['sudo -v'])

    @unittest.skipIf(os.geteuid() == 0, 'Le script refuse le compte root.')
    def test_restore_does_not_request_sudo(self):
        result, calls = self.run_phase('restore')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len(calls), 1)
        self.assertTrue(calls[0].startswith('python '))


if __name__ == '__main__':
    unittest.main()
