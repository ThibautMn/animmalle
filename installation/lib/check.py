"""Contrôle préalable sans sudo ni modification : YAML, permissions et rendu du déploiement.

Toutes les validations de la configuration sont faites ici, avant toute action système,
pour qu'une erreur de YAML soit signalée au début de l'installation et non au milieu.
Sortie standard : faits utiles au script Bash, au format CLE=valeur. Erreurs : stderr.
"""

import os
from pathlib import Path
import stat
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'backend'))
sys.path.insert(0, str(Path(__file__).resolve().parent))

LOCAL_HOSTS = {'localhost', '127.0.0.1', '::1'}


def is_local(url):
    """PostgreSQL local, quel que soit le port : administré via le compte système postgres."""
    return url.host in LOCAL_HOSTS


def check_file(path):
    if not path.is_file():
        raise ValueError('Créer installation/config_principal.yaml depuis config_principal.example.yaml, puis chmod 600.')
    info = path.stat()
    if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) & 0o077:
        raise ValueError('installation/config_principal.yaml doit appartenir au compte courant avec les permissions 600 ou 400 (chmod 600).')


def check_database(path):
    from animmalle.config import load_database_url

    url = load_database_url(path)
    if url.password == 'REMPLACER':
        raise ValueError('Renseigner postgresql.password dans le YAML.')
    if url.database in {'postgres', 'template0', 'template1'}:
        raise ValueError('postgresql.database : choisir une base applicative distincte des bases système.')
    return url


def load_deploy_config(path):
    """Paramètres validés par le backend, complétés des sections nginx et nuxt."""
    import yaml
    from animmalle.config import load_settings

    config = load_settings(path)
    raw = yaml.safe_load(Path(path).read_text(encoding='utf-8'))
    for key in ('nginx', 'nuxt'):
        if not isinstance(raw.get(key), dict):
            raise ValueError(f'Section {key} requise dans le YAML (voir config_principal.example.yaml).')
        config[key] = raw[key]
    return config


def main(argv):
    from animmalle.config import CONFIG_PATH

    if argv not in (['database'], ['full']):
        raise ValueError('Utilisation : check.py database|full')
    check_file(CONFIG_PATH)
    url = check_database(CONFIG_PATH)
    facts = {'PG_LOCAL': '1' if is_local(url) else '0', 'PG_PORT': str(url.port)}
    if argv == ['full']:
        import deploy

        config = load_deploy_config(CONFIG_PATH)
        # Node peut ne pas encore être installé : un chemin fictif suffit à valider le rendu.
        deploy.render(config, node=os.environ.get('ANIMMALLE_NODE') or '/usr/bin/node')
    for key, value in facts.items():
        print(f'{key}={value}')


if __name__ == '__main__':
    try:
        main(sys.argv[1:])
    except ValueError as error:
        print(f'Configuration invalide : {error}', file=sys.stderr)
        sys.exit(1)
    except KeyError as error:
        print(f'Configuration invalide : clé {error} absente du YAML (voir config_principal.example.yaml).', file=sys.stderr)
        sys.exit(1)
    except Exception as error:
        # Les messages externes peuvent contenir des secrets : seul le type est affiché.
        print(f'Contrôle de configuration impossible ({type(error).__module__}.{type(error).__name__}).', file=sys.stderr)
        sys.exit(1)
