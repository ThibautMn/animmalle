"""Lecture de la connexion depuis l'unique configuration YAML centrale."""

from pathlib import Path

import yaml
from sqlalchemy.engine import URL

CONFIG_PATH = Path(__file__).resolve().parents[2] / 'installation' / 'config_principal.yaml'


def load_database_url(path=CONFIG_PATH):
    try:
        with Path(path).open(encoding='utf-8') as stream:
            data = yaml.safe_load(stream)
    except (OSError, yaml.YAMLError):
        raise ValueError('Configuration YAML centrale absente ou illisible.') from None
    pg = data.get('postgresql') if isinstance(data, dict) else None
    if not isinstance(pg, dict):
        raise ValueError('Section postgresql requise.')
    for key in ('host', 'database', 'username', 'password'):
        if not isinstance(pg.get(key), str) or not pg[key].strip():
            raise ValueError(f'Champ postgresql.{key} requis et non vide.')
    port = pg.get('port')
    if type(port) is not int or not 1 <= port <= 65535:
        raise ValueError('Port PostgreSQL invalide.')
    return URL.create('postgresql+psycopg', username=pg['username'],
                      password=pg['password'], host=pg['host'], port=port,
                      database=pg['database'])
