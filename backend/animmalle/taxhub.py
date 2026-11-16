"""Client minimal de l'API TaxHub du PNC : recherche Taxref, médias d'un taxon, import d'un média."""
import io
import json
import time
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from pathlib import PurePosixPath
from urllib.error import URLError
from urllib.parse import quote, unquote, urlencode, urlsplit
from urllib.request import Request, urlopen

from flask import abort, current_app, g
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from .models import TaxonMedia

DEFAULT_API_URL = 'https://appli.cevennes-parcnational.net/geonature/api/taxhub/api'
TIMEOUT = 15


def api_url():
    return current_app.extensions['settings'].get('taxhub', {}).get('api_url', DEFAULT_API_URL).rstrip('/')


def _get(url, limit):
    request = Request(url, headers={'Accept': '*/*', 'User-Agent': 'animmalle'})
    try:
        with urlopen(request, timeout=TIMEOUT) as response:
            content = response.read(limit + 1)
    except (URLError, OSError, ValueError):
        abort(502, description='TaxHub est indisponible.')
    if len(content) > limit:
        abort(422, description='Fichier trop volumineux.')
    return content


def _json(path, params=None):
    url = f'{api_url()}/{path}' + (f'?{urlencode(params)}' if params else '')
    try:
        return json.loads(_get(url, 10 * 1024 * 1024))
    except ValueError:
        abort(502, description='Réponse TaxHub invalide.')


# Taxons dont TaxHub publie au moins un média : conservés en base (table taxon_media), car ces médias disparaissent
# très rarement. Seuls les taxons sans média sont revérifiés (mémoire, quelques minutes).
_NO_MEDIA = {}
_CACHE_SECONDS = 600
# TaxHub n'en renvoie que 20 par défaut : on en examine davantage pour ne pas perdre de taxons illustrés.
MAX_CANDIDATES = 100


def _known(cd_refs):
    """cd_ref déjà enregistrés ; base indisponible ou table absente : aucun (TaxHub est alors interrogé)."""
    try:
        return set(g.db.scalars(select(TaxonMedia.cd_ref).where(TaxonMedia.cd_ref.in_(cd_refs))))
    except SQLAlchemyError:
        g.db.rollback()
        return set()


def _remember(taxa):
    """Enregistre les nouveaux taxons illustrés ; l'enregistrement n'est qu'un accélérateur et n'échoue jamais."""
    for item in taxa:
        try:
            with g.db.begin_nested():
                g.db.add(TaxonMedia(cd_ref=item['cd_ref'], lb_nom=(item['lb_nom'] or '')[:250],
                                    nom_vern=item['nom_vern'], nom_valide=item['nom_valide'],
                                    group2_inpn=(item['group2_inpn'] or None) and item['group2_inpn'][:100]))
            g.db.commit()
        except SQLAlchemyError:
            # Déjà enregistré par une requête concurrente, ou table absente.
            g.db.rollback()


def _has_media(base, cd_ref, known):
    """Vrai/faux selon TaxHub, None si TaxHub ne répond pas ; les taxons connus ne sont pas réinterrogés."""
    if cd_ref in known:
        return True
    failed = _NO_MEDIA.get(cd_ref)
    if failed and time.monotonic() - failed < _CACHE_SECONDS:
        return False
    try:
        rows = json.loads(_get(f'{base}/tmedias/bycdref/{cd_ref}', 10 * 1024 * 1024))
    except Exception:
        return None
    if isinstance(rows, list) and rows:
        return True
    if len(_NO_MEDIA) > 5000:
        _NO_MEDIA.clear()
    _NO_MEDIA[cd_ref] = time.monotonic()
    return False


def _plain(text):
    return unicodedata.normalize('NFD', text).encode('ascii', 'ignore').decode().casefold()


def _sort_key(item, term=''):
    """Classement : nom vernaculaire commençant par la saisie, puis le contenant, puis les autres noms
    vernaculaires, enfin les taxons sans nom vernaculaire (ceux dont le nom scientifique commence par la saisie
    d'abord). Dans chaque groupe : ordre alphabétique du premier nom vernaculaire, sans casse ni accents."""
    term = _plain(term.strip())
    names = [_plain(name.strip()) for name in (item.get('nom_vern') or '').split(',') if name.strip()]
    latin = _plain(item.get('lb_nom') or '')
    if names:
        group = 0 if any(name.startswith(term) for name in names) else 1 if any(term in name for name in names) else 2
    else:
        group = 3 if latin.startswith(term) else 4
    return (group, names[0] if names else '', latin)


def search_taxa(term):
    rows = _json('taxref/allnamebylist', {'search_name': term, 'limit': MAX_CANDIDATES})
    if not isinstance(rows, list):
        abort(502, description='Réponse TaxHub invalide.')
    candidates = [{key: row.get(key) for key in ('cd_ref', 'lb_nom', 'nom_vern', 'nom_valide', 'group2_inpn')}
                  for row in rows[:MAX_CANDIDATES] if isinstance(row, dict) and type(row.get('cd_ref')) is int]
    # Les synonymes partagent le cd_ref de leur taxon de référence : une seule entrée par cd_ref.
    seen = set()
    candidates = [item for item in candidates if item['cd_ref'] not in seen and not seen.add(item['cd_ref'])]
    # Seuls les taxons ayant au moins un média sont proposés ; un échec ponctuel de TaxHub ne masque pas le taxon.
    base = api_url()
    known = _known([item['cd_ref'] for item in candidates])
    with ThreadPoolExecutor(max_workers=20) as pool:
        flags = list(pool.map(lambda item: _has_media(base, item['cd_ref'], known), candidates))
    _remember([item for item, flag in zip(candidates, flags) if flag and item['cd_ref'] not in known])
    result = [item for item, flag in zip(candidates, flags) if flag is not False]
    result.sort(key=lambda item: _sort_key(item, term))
    return result


def taxon(cd_ref):
    row = _json(f'taxref/{int(cd_ref)}')
    if not isinstance(row, dict):
        abort(502, description='Réponse TaxHub invalide.')
    return {key: row.get(key) for key in ('cd_nom', 'cd_ref', 'lb_nom', 'nom_valide', 'nom_vern', 'regne', 'group2_inpn')}


def media_list(cd_ref):
    rows = _json(f'tmedias/bycdref/{int(cd_ref)}')
    if not isinstance(rows, list):
        abort(502, description='Réponse TaxHub invalide.')
    return [{'id_media': row['id_media'], 'titre': row.get('titre') or '', 'auteur': row.get('auteur') or '',
             'source': row.get('source') or '', 'licence': row.get('licence') or '', 'id_type': row.get('id_type'),
             'url': row.get('media_url') or row.get('url') or ''}
            for row in rows if isinstance(row, dict) and type(row.get('id_media')) is int
            and urlsplit(row.get('media_url') or row.get('url') or '').scheme in ('http', 'https')]


class Download:
    """Fichier téléchargé, compatible avec files.store_upload."""

    def __init__(self, filename, content):
        self.filename = filename
        self.stream = io.BytesIO(content)


def download_media(cd_ref, id_media, limit):
    """Télécharge un média déjà publié par TaxHub pour ce taxon ; aucune URL libre n'est acceptée."""
    media = next((item for item in media_list(cd_ref) if item['id_media'] == id_media), None)
    if media is None:
        abort(404, description='Média TaxHub introuvable.')
    parts = urlsplit(media['url'])
    name = PurePosixPath(unquote(parts.path)).name
    # Espaces ou accents du chemin source : réencodage avant la requête.
    url = parts._replace(path=quote(unquote(parts.path))).geturl()
    return media, Download(name, _get(url, limit))
