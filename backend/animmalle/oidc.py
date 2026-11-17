"""Connexion OpenID Connect (flux « authorization code » avec PKCE).

Le navigateur est redirigé vers le fournisseur, qui renvoie un `code` sur
`auth.oidc.redirect_uri` (page du frontend). Le frontend transmet ce code au
backend, qui l'échange contre un jeton avec le secret client (qui ne quitte
jamais le serveur), puis lit les informations de l'utilisateur sur le point
d'accès userinfo. Le compte est ensuite cherché par login dans la configuration
locale ou l'annuaire LDAP : aucun compte n'est créé, un inconnu est refusé.
"""
import base64
import json
import re
import urllib.error
import urllib.parse
import urllib.request

from flask import current_app

TIMEOUT = 10
# PKCE (RFC 7636) : empreinte SHA-256 en base64url, code_verifier de 43 à 128 caractères
RE_CHALLENGE = re.compile(r'^[A-Za-z0-9_-]{43}$')
RE_VERIFIER = re.compile(r'^[A-Za-z0-9._~-]{43,128}$')
RE_STATE = re.compile(r'^[A-Za-z0-9._~-]{8,128}$')

_discovery = {}


class InvalidOidcAuth(Exception):
    """Code refusé par le fournisseur."""


def settings():
    return current_app.extensions['settings']['auth']['oidc']


def is_enabled():
    cfg = settings()
    return bool(cfg['discovery_url'] and cfg['client_id'])


def only_oidc():
    """Connexion par le fournisseur uniquement ; sans effet si OIDC est désactivé."""
    return is_enabled() and settings()['only_oidc_connexion']


def _http_json(req):
    with urllib.request.urlopen(req, timeout=TIMEOUT) as response:
        return json.loads(response.read().decode('utf-8'))


def discovery():
    """Document de découverte du fournisseur, lu une fois par processus et par URL."""
    url = settings()['discovery_url']
    if url not in _discovery:
        _discovery[url] = _http_json(url)
    return _discovery[url]


def authorize_url(state, code_challenge, silent=False):
    """`silent` : prompt=none, le fournisseur ne montre aucune page et renvoie un code ou une erreur."""
    cfg = settings()
    params = {'response_type': 'code', 'client_id': cfg['client_id'], 'redirect_uri': cfg['redirect_uri'],
              'scope': cfg['scope'], 'state': state, 'code_challenge': code_challenge,
              'code_challenge_method': 'S256'}
    if silent:
        params['prompt'] = 'none'
    return discovery()['authorization_endpoint'] + '?' + urllib.parse.urlencode(params)


def exchange_code(code, code_verifier):
    """Échange le code contre un jeton puis renvoie les claims userinfo."""
    cfg = settings()
    disc = discovery()
    form = {'grant_type': 'authorization_code', 'code': code, 'redirect_uri': cfg['redirect_uri'],
            'code_verifier': code_verifier}
    headers = {'Accept': 'application/json'}
    methods = disc.get('token_endpoint_auth_methods_supported', ['client_secret_basic'])
    if 'client_secret_post' in methods:
        form['client_id'] = cfg['client_id']
        form['client_secret'] = cfg['client_secret']
    else:
        credentials = '%s:%s' % (urllib.parse.quote(cfg['client_id'], safe=''),
                                 urllib.parse.quote(cfg['client_secret'], safe=''))
        headers['Authorization'] = 'Basic ' + base64.b64encode(credentials.encode('utf-8')).decode('ascii')
    try:
        tokens = _http_json(urllib.request.Request(disc['token_endpoint'], data=urllib.parse.urlencode(form).encode('utf-8'),
                                                   headers=headers, method='POST'))
        return _http_json(urllib.request.Request(disc['userinfo_endpoint'], headers={
            'Authorization': 'Bearer ' + tokens['access_token'], 'Accept': 'application/json'}))
    except (urllib.error.HTTPError, KeyError) as error:
        raise InvalidOidcAuth from error


def login_from_claims(claims):
    """Login du compte : `preferred_username` ou `sub`, jamais l'e-mail (modifiable par l'utilisateur)."""
    login = claims.get('preferred_username') or claims.get('sub') or ''
    return login.strip() if isinstance(login, str) else ''
