"""Authentification locale hachée ou LDAP et session signée."""
import secrets
import ssl

from flask import current_app, g, request, session, abort
from werkzeug.security import check_password_hash


def directory_tls(cfg):
    import ldap3
    return ldap3.Tls(validate=ssl.CERT_REQUIRED, ca_certs_file=cfg.get('ca_certs_file') or None)


def close_directory(connection):
    import ldap3
    if connection is not None:
        try:
            connection.unbind()
        except (ldap3.core.exceptions.LDAPException, OSError):
            pass


def authenticate(login, password):
    config = current_app.extensions['settings']['auth']
    if config['mode'] == 'local':
        for user in config['users']:
            if secrets.compare_digest(user['login'], login) and check_password_hash(user['password_hash'], password):
                return {'name': user['name'], 'groups': user['groups']}
        return None
    import ldap3
    from ldap3.utils.conv import escape_filter_chars
    from ldap3.utils.dn import escape_rdn, parse_dn
    cfg = config['ldap']
    connection = None
    try:
        server = ldap3.Server(cfg['host'], port=cfg['port'], use_ssl=cfg['ssl'],
                              tls=directory_tls(cfg) if cfg['ssl'] or cfg.get('start_tls', True) else None,
                              connect_timeout=cfg['timeout'])
        connection = ldap3.Connection(server, user=cfg['user_dn'].replace('{login}', escape_rdn(login)),
                                      password=password, receive_timeout=cfg['timeout'], auto_referrals=False)
        if not cfg['ssl'] and cfg.get('start_tls', True):
            connection.open()
            if not connection.start_tls():
                abort(503, description='Connexion TLS à l’annuaire impossible.')
        if not connection.bind():
            return None
        if not connection.search(cfg['base_dn'], f"({cfg['login_attribute']}={escape_filter_chars(login)})",
                                 attributes=[cfg['name_attribute'], cfg['group_attribute']], size_limit=2):
            return None
        if len(connection.entries) != 1:
            return None
        data = connection.entries[0].entry_attributes_as_dict
        names = data.get(cfg['name_attribute'], [])
        if not names or len(str(names[0])) > 100:
            return None
        groups = [parse_dn(value)[0][1] for value in data.get(cfg['group_attribute'], [])]
        return {'name': str(names[0]), 'groups': groups}
    except (ldap3.core.exceptions.LDAPException, ValueError, OSError):
        abort(503, description='Annuaire indisponible.')
    finally:
        close_directory(connection)


def install_auth(app):
    @app.before_request
    def guard():
        if not request.path.startswith('/api/') or request.path == '/api/health' or request.method == 'OPTIONS':
            return
        origin = request.headers.get('Origin')
        allowed = {app.extensions['settings']['public'][key].rstrip('/') for key in ('frontend_url', 'api_url')}
        if origin and origin not in allowed:
            abort(403, description='Origine refusée.')
        if 'csrf_token' not in session:
            session['csrf_token'] = secrets.token_urlsafe(32)
        if request.method not in ('GET', 'HEAD', 'OPTIONS'):
            token = request.headers.get('X-CSRF-Token', '')
            if not secrets.compare_digest(token, session['csrf_token']):
                abort(403, description='Jeton CSRF manquant ou invalide.')
        if request.path in ('/api/auth/login', '/api/auth/session'):
            return
        user = session.get('user')
        if not user:
            abort(401, description='Authentification requise.')
        g.user = user
        g.is_admin = bool(set(user['groups']) & set(app.extensions['settings']['auth']['admin_groups']))


def login_user(user):
    session.clear()
    session['user'] = user
    session['csrf_token'] = secrets.token_urlsafe(32)
    session.permanent = True


def require_admin():
    if not g.is_admin:
        abort(403, description='Droits administrateur requis.')


def directory_users(prefix):
    """Autocomplétion LDAP facultative avec un compte de lecture dédié."""
    config = current_app.extensions['settings']['auth']
    if config['mode'] == 'local':
        return sorted({u['name'] for u in config['users'] if u['name'].casefold().startswith(prefix.casefold())})[:100]
    cfg = config['ldap']
    if not cfg.get('service_bind_dn') or not cfg.get('service_password'):
        return None
    import ldap3
    from ldap3.utils.conv import escape_filter_chars
    connection = None
    try:
        server = ldap3.Server(cfg['host'], port=cfg['port'], use_ssl=cfg['ssl'],
                              tls=directory_tls(cfg) if cfg['ssl'] or cfg.get('start_tls', True) else None,
                              connect_timeout=cfg['timeout'])
        connection = ldap3.Connection(server, user=cfg['service_bind_dn'], password=cfg['service_password'],
                                      receive_timeout=cfg['timeout'], auto_referrals=False)
        if not cfg['ssl'] and cfg.get('start_tls', True):
            connection.open()
            if not connection.start_tls():
                abort(503, description='Connexion TLS à l’annuaire impossible.')
        if not connection.bind():
            abort(503, description='Annuaire indisponible.')
        if not connection.search(cfg['base_dn'], f"({cfg['name_attribute']}={escape_filter_chars(prefix)}*)",
                                 attributes=[cfg['name_attribute']], size_limit=100):
            if connection.result.get('result') not in (0, 4):
                abort(503, description='Annuaire indisponible.')
        return sorted({str(entry[cfg['name_attribute']]) for entry in connection.entries})
    except (ldap3.core.exceptions.LDAPException, ValueError, OSError):
        abort(503, description='Annuaire indisponible.')
    finally:
        close_directory(connection)
