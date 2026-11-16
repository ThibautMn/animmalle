"""Lecture de la connexion depuis l'unique configuration YAML centrale."""

from pathlib import Path
from urllib.parse import urlsplit

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


def load_settings(path=CONFIG_PATH):
    """Valide les paramètres applicatifs ; aucune valeur secrète par défaut."""
    try:
        with Path(path).open(encoding='utf-8') as stream:
            data = yaml.safe_load(stream)
    except (OSError, yaml.YAMLError):
        raise ValueError('Configuration YAML centrale absente ou illisible.') from None
    if not isinstance(data, dict):
        raise ValueError('Configuration YAML invalide.')
    for section in ('backend', 'auth', 'paths', 'public', 'gunicorn', 'proxy'):
        if not isinstance(data.get(section), dict):
            raise ValueError(f'Section {section} requise ; consulter le fichier exemple.')
    backend = data['backend']
    if not isinstance(backend.get('secret_key'), str) or len(backend['secret_key']) < 32 or backend['secret_key'].startswith('REMPLACER'):
        raise ValueError('backend.secret_key : secret aléatoire de 32 caractères minimum requis.')
    for key in ('frontend_url', 'api_url'):
        value = data['public'].get(key)
        parsed = urlsplit(value) if isinstance(value, str) else None
        if not parsed or parsed.scheme not in ('http', 'https') or not parsed.netloc or parsed.query or parsed.fragment or parsed.username or parsed.path not in ('', '/'):
            raise ValueError(f'public.{key} doit être une origine HTTP(S).')
    for key in ('cookie_secure',):
        if type(backend.get(key)) is not bool:
            raise ValueError(f'backend.{key} doit être un booléen.')
    if backend.get('cookie_samesite') not in ('Lax', 'Strict', 'None'):
        raise ValueError('backend.cookie_samesite invalide.')
    if backend['cookie_samesite'] == 'None' and not backend['cookie_secure']:
        raise ValueError('SameSite=None requiert cookie_secure=true.')
    for key in ('session_hours', 'max_upload_mb'):
        if type(backend.get(key)) is not int or not 1 <= backend[key] <= 1024:
            raise ValueError(f'backend.{key} invalide.')
    for key in ('x_for', 'x_proto', 'x_host', 'x_port', 'x_prefix'):
        if type(data['proxy'].get(key)) is not int or not 0 <= data['proxy'][key] <= 10:
            raise ValueError(f'proxy.{key} invalide.')
    auth = data['auth']
    if auth.get('mode') not in ('ldap', 'local') or not isinstance(auth.get('admin_groups'), list) or not all(isinstance(x, str) for x in auth['admin_groups']):
        raise ValueError('Configuration auth invalide.')
    if 'thesaurus_groups' in auth and (not isinstance(auth['thesaurus_groups'], list) or not all(isinstance(x, str) for x in auth['thesaurus_groups'])):
        raise ValueError('auth.thesaurus_groups invalide.')
    if auth['mode'] == 'local':
        if not isinstance(auth.get('users'), list) or not auth['users']:
            raise ValueError('auth.users requis en mode local (mots de passe hachés).')
        for user in auth['users']:
            if not isinstance(user, dict) or not all(isinstance(user.get(k), str) and user[k] for k in ('login', 'name', 'password_hash')) or len(user['name']) > 100 or not isinstance(user.get('groups'), list) or not all(isinstance(g, str) for g in user['groups']):
                raise ValueError('Compte local invalide.')
        if len({u['login'] for u in auth['users']}) != len(auth['users']) or len({u['name'] for u in auth['users']}) != len(auth['users']):
            raise ValueError('Les identités locales doivent être uniques.')
    else:
        ldap = auth.get('ldap', {})
        if not isinstance(ldap, dict):
            raise ValueError('Configuration LDAP invalide.')
        for key in ('host', 'base_dn', 'user_dn', 'login_attribute', 'name_attribute', 'group_attribute'):
            if not isinstance(ldap.get(key), str) or not ldap[key]:
                raise ValueError(f'auth.ldap.{key} requis.')
        import re
        if not all(re.fullmatch(r'[A-Za-z][A-Za-z0-9-]*', ldap[k]) for k in ('login_attribute', 'name_attribute', 'group_attribute')):
            raise ValueError('Attribut LDAP invalide.')
        if '{login}' not in ldap['user_dn'] or type(ldap.get('port')) is not int or not 1 <= ldap['port'] <= 65535 or type(ldap.get('ssl')) is not bool or type(ldap.get('timeout')) is not int or not 1 <= ldap['timeout'] <= 60:
            raise ValueError('Configuration LDAP invalide.')
        if type(ldap.get('start_tls', True)) is not bool:
            raise ValueError('auth.ldap.start_tls doit être un booléen.')
    root = Path(__file__).resolve().parents[2]
    if auth['mode'] == 'ldap':
        ca_file = auth['ldap'].get('ca_certs_file')
        if ca_file not in (None, ''):
            if not isinstance(ca_file, str) or not ca_file.strip():
                raise ValueError('auth.ldap.ca_certs_file doit être un chemin de certificat PEM.')
            ca_path = (root / ca_file).resolve()
            if not ca_path.is_file():
                raise ValueError('auth.ldap.ca_certs_file : fichier introuvable.')
            auth['ldap']['ca_certs_file'] = str(ca_path)
    for key in ('uploads', 'pages', 'pictograms'):
        value = data['paths'].get(key)
        if not isinstance(value, str) or not value:
            raise ValueError(f'paths.{key} requis.')
        data['paths'][key] = (root / value).resolve()
    if data['paths'].get('thumbnails') not in (None, ''):
        if not isinstance(data['paths']['thumbnails'], str):
            raise ValueError('paths.thumbnails doit être un chemin.')
        data['paths']['thumbnails'] = (root / data['paths']['thumbnails']).resolve()
    historical_root = root / 'ancien_animalle'
    for key in ('uploads', 'pages', 'thumbnails'):
        if data['paths'].get(key) and data['paths'][key].is_relative_to(historical_root):
            raise ValueError('Les répertoires modifiables doivent être hors du dossier historique.')
    extensions = backend.get('allowed_extensions')
    if not isinstance(extensions, list) or not extensions or not all(isinstance(x, str) and x.isalnum() for x in extensions):
        raise ValueError('backend.allowed_extensions invalide.')
    gunicorn = data['gunicorn']
    if not isinstance(gunicorn.get('bind'), str) or not gunicorn['bind'] or any(type(gunicorn.get(k)) is not int or gunicorn[k] < 1 for k in ('workers', 'timeout')):
        raise ValueError('Configuration gunicorn invalide.')
    taxhub = data.get('taxhub', {})
    if not isinstance(taxhub, dict):
        raise ValueError('Configuration taxhub invalide.')
    if 'api_url' in taxhub:
        parsed = urlsplit(taxhub['api_url']) if isinstance(taxhub['api_url'], str) else None
        if not parsed or parsed.scheme not in ('http', 'https') or not parsed.netloc or parsed.query or parsed.fragment or parsed.username:
            raise ValueError('taxhub.api_url doit être une adresse HTTP(S).')
    mail = data.get('mail', {})
    if not isinstance(mail, dict) or type(mail.get('enabled', False)) is not bool:
        raise ValueError('Configuration mail invalide.')
    if mail.get('enabled'):
        if not all(isinstance(mail.get(k), str) and mail[k] and '\n' not in mail[k] and '\r' not in mail[k] for k in ('host', 'sender')) or type(mail.get('port')) is not int or not 1 <= mail['port'] <= 65535 or type(mail.get('starttls')) is not bool:
            raise ValueError('Configuration SMTP invalide.')
        if not isinstance(mail.get('recipients'), list) or not mail['recipients'] or not all(isinstance(x, str) and '@' in x and '\n' not in x and '\r' not in x for x in mail['recipients']):
            raise ValueError('mail.recipients requis.')
    return data
