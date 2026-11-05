"""Lancer depuis la racine ; la configuration reste dans le YAML central."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from animmalle.config import load_settings

_settings = load_settings()
bind = _settings['gunicorn']['bind']
workers = _settings['gunicorn']['workers']
timeout = _settings['gunicorn']['timeout']
# Les en-têtes proxy sont traités uniquement par ProxyFix selon le YAML.
forwarded_allow_ips = ''
accesslog = None
errorlog = '-'
wsgi_app = 'animmalle:create_app()'
