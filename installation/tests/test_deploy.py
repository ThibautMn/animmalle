"""Validation du rendu uniquement : aucun sudo, service, réseau ou base."""
import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('deploy', Path(__file__).resolve().parents[1] / 'lib/deploy.py')
deploy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(deploy)


class DeployTests(unittest.TestCase):
    def config(self):
        return {'public': {'frontend_url': 'https://app.example.org', 'api_url': 'https://api.example.org'},
                'nuxt': {'port': 3000}, 'gunicorn': {'bind': '127.0.0.1:8000'},
                'nginx': {'listen': '127.0.0.1:8080', 'upstream_tls': True},
                'backend': {'max_upload_mb': 64, 'secret_key': 'SECRET'}, 'postgresql': {'password': 'SECRET'}}

    def test_routing_and_headers_without_secrets(self):
        output = deploy.render(self.config(), root=Path('/srv/animmalle'), node='/usr/bin/node', user='app')
        nginx = output['animmalle.conf']
        self.assertIn('location /api/', nginx)
        self.assertIn('location / { return 404; }', nginx)
        self.assertIn('proxy_set_header X-Forwarded-Proto https;', nginx)
        self.assertIn('proxy_set_header X-Forwarded-For $remote_addr;', nginx)
        self.assertIn('127.0.0.1:3000', nginx)
        self.assertNotIn('SECRET', str(output))
        self.assertIn('NITRO_HOST=127.0.0.1', output['animmalle-frontend.service'])

    def test_rejects_public_upstream_and_injection(self):
        for value in ('0.0.0.0:8080', '127.0.0.1:8080;bad', '127.0.0.1:99999'):
            config = self.config()
            config['nginx']['listen'] = value
            with self.assertRaises(ValueError):
                deploy.render(config, node='/usr/bin/node', user='app')
        config = self.config()
        config['public']['api_url'] = 'https://api.example.org;evil'
        with self.assertRaises(ValueError):
            deploy.render(config, node='/usr/bin/node', user='app')

    def test_direct_tls_requires_certificates(self):
        config = self.config()
        config['nginx'] = {'listen': '0.0.0.0:443', 'upstream_tls': False}
        with self.assertRaises(ValueError):
            deploy.render(config, node='/usr/bin/node', user='app')
        config['nginx'].update(certificate='/etc/cert.pem', certificate_key='/etc/key.pem')
        output = deploy.render(config, node='/usr/bin/node', user='app')
        self.assertIn('listen 0.0.0.0:443 ssl;', output['animmalle.conf'])
        self.assertIn('X-Forwarded-Proto $scheme;', output['animmalle.conf'])
