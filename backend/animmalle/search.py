"""Recherche générale : découpage en mots (ET) et extraits entourant les termes trouvés."""
import html
import re
import unicodedata

from marshmallow import ValidationError
from sqlalchemy import String, event
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.sql.expression import FunctionElement

MAX_TERM_LENGTH = 100
MAX_TERMS = 10
SNIPPET_RADIUS = 70
MAX_SNIPPETS = 5

_BLOCK_END = re.compile(r'</(p|li|h[1-6]|tr|blockquote)>|<br\s*/?>', re.IGNORECASE)
_TAG = re.compile(r'<[^>]+>')
_SPACES = re.compile(r'\s+')


def _fold_char(char):
    base = unicodedata.normalize('NFD', char)[0].lower()
    return base if len(base) == 1 else char


def fold(text):
    """Texte sans accents ni majuscules, de même longueur (positions conservées)."""
    return ''.join(_fold_char(char) for char in text)


_ACCENTED = ''.join(char for char in map(chr, range(0xC0, 0x180)) if fold(char) != char.lower() or char != char.lower())
_ACCENTED = ''.join(char for char in _ACCENTED if fold(char) != char and fold(char).isascii())
_PLAIN = fold(_ACCENTED)


class folded(FunctionElement):
    """Colonne ramenée en minuscules sans accents (équivalent SQL de `fold`)."""
    type = String()
    inherit_cache = True
    name = 'folded'


@compiles(folded)
def _folded_default(element, compiler, **kw):
    column = compiler.process(element.clauses, **kw)
    return f"lower(translate({column}, '{_ACCENTED}', '{_PLAIN}'))"


@compiles(folded, 'sqlite')
def _folded_sqlite(element, compiler, **kw):
    return f'fold({compiler.process(element.clauses, **kw)})'


def install(engine):
    """SQLite (développement, tests) : déclare `fold`, absente du moteur ; sans effet sur PostgreSQL."""
    if engine.dialect.name != 'sqlite':
        return

    @event.listens_for(engine, 'checkout')
    def register(connection, _record, _proxy):
        connection.create_function('fold', 1, lambda value: None if value is None else fold(value), deterministic=True)


def split_terms(values):
    """Mots d'une ou plusieurs saisies : séparés par des espaces, sans doublon (casse ignorée).

    Tous les mots doivent être trouvés (ET), sans ordre ni adjacence imposés.
    """
    terms = []
    seen = set()
    for value in values:
        for word in value.split():
            if len(word) > MAX_TERM_LENGTH:
                raise ValidationError({'q': [f'{MAX_TERM_LENGTH} caractères maximum par mot.']})
            if fold(word) not in seen:
                seen.add(fold(word))
                terms.append(word)
    if len(terms) > MAX_TERMS:
        raise ValidationError({'q': [f'{MAX_TERMS} mots maximum.']})
    return terms


def like_pattern(term):
    escaped = fold(term).replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')
    return f'%{escaped}%'


def plain_text(value):
    """Texte brut d'un contenu éventuellement issu de l'éditeur riche."""
    if not value:
        return ''
    value = _TAG.sub(' ', _BLOCK_END.sub('\n', value)) if '<' in value else value
    return _SPACES.sub(' ', html.unescape(value)).strip()


def first_lines(value, lines=4, limit=400):
    """Début d'un contenu : ses premières lignes (paragraphes), tronquées à `limit` caractères."""
    if not value:
        return ''
    value = _TAG.sub(' ', _BLOCK_END.sub('\n', value)) if '<' in value else value
    rows = [_SPACES.sub(' ', row).strip() for row in html.unescape(value).split('\n')]
    text = '\n'.join([row for row in rows if row][:lines])
    if len(text) > limit:
        cut = text.rfind(' ', 0, limit)
        text = text[:cut if cut > 0 else limit].rstrip() + '…'
    return text


def after_start(value, start):
    """Texte brut de `value` privé de son début déjà affiché (`start`, issu de first_lines)."""
    full = plain_text(value)
    shown = plain_text(start.removesuffix('…'))
    return full[len(shown):].strip() if shown and full.startswith(shown) else full


def _window(text, start, end):
    """Fenêtre de `text` autour de [start, end), coupée aux limites de mots."""
    left = max(0, start - SNIPPET_RADIUS)
    right = min(len(text), end + SNIPPET_RADIUS)
    if left > 0:
        space = text.find(' ', left, start)
        left = space + 1 if space != -1 else left
    if right < len(text):
        space = text.rfind(' ', end, right)
        right = space if space != -1 else right
    return ('…' if left > 0 else '') + text[left:right].strip() + ('…' if right < len(text) else '')


def snippet(text, terms):
    """Extrait autour de la première occurrence ; renvoie (extrait, nombre de mots distincts trouvés)."""
    plain = fold(text)
    found = [(plain.find(fold(term)), term) for term in terms]
    found = [(position, term) for position, term in found if position != -1]
    if not found:
        return None, 0
    position, term = min(found)
    return _window(text, position, position + len(term)), len(found)


def build_snippets(fields, terms, limit=MAX_SNIPPETS):
    """Extraits des champs (source, contenu) : d'abord ceux qui contiennent le plus de mots recherchés."""
    if not terms:
        return []
    ranked = []
    for order, (source, content) in enumerate(fields):
        text = plain_text(content)
        extract, count = snippet(text, terms) if text else (None, 0)
        if extract:
            ranked.append((-count, order, {'source': source, 'text': extract}))
    return [item for _, _, item in sorted(ranked, key=lambda entry: entry[:2])[:limit]]
