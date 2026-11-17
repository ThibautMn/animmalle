"""Reprise de données MariaDB : aucun ordre SQL source n'est exécuté."""

from datetime import date
from pathlib import Path
import re

from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import Date, Integer, String, UniqueConstraint, inspect, select, text
from animmalle.models import APPLICATION_TABLES, Base

ALEMBIC_INI = Path(__file__).resolve().parents[2] / 'backend' / 'alembic.ini'


def head_revisions():
    """Révision(s) la plus récente des migrations ; lecture des fichiers, sans connexion."""
    return sorted(ScriptDirectory.from_config(Config(str(ALEMBIC_INI))).get_heads())


# Tables du dump historique : celles propres à la nouvelle application n'en font pas partie.
HISTORICAL = {name: table for name, table in Base.metadata.tables.items() if name not in APPLICATION_TABLES}
# Colonnes de l'ancien dump remplacées depuis : table -> (colonne historique, colonne actuelle).
RENAMED = {'sequence': ('fk_duree_id', 'duree_minutes')}
# Colonnes absentes de l'ancien dump, calculées à l'import : table -> colonnes.
ADDED = {'thesaurus': {'position'}}
# Tables du dump absentes des modèles actuels : `mat_peda` est séparée en `media` et `outil_facilitateur`.
SOURCE_ONLY = {
    'mat_peda': ['id', 'fk_type_mat_id', 'nom', 'description', 'url', 'localisation', 'variante',
                 'difficulte_id', 'materiel', 'date_modif', 'fk_type_mat_outil_id'],
    'rel_mat_peda_sequence': ['id', 'fk_mat_peda_id', 'fk_sequence_id'],
    'rel_mat_peda_thematique': ['id', 'fk_mat_peda_id', 'fk_thes_id'],
}
# Tables actuelles construites à l'import à partir des précédentes.
DERIVED = {'media', 'outil_facilitateur', 'rel_media_sequence', 'rel_media_thematique'}
SOURCE_TABLES = (set(HISTORICAL) - DERIVED) | set(SOURCE_ONLY)
HISTORICAL_SORTED = [table for table in Base.metadata.sorted_tables if table.name in HISTORICAL]


def statements(source):
    """Découper hors chaînes/commentaires, y compris les commentaires exécutables."""
    position = 0
    current = []
    quoted = False
    while position < len(source):
        char = source[position]
        if quoted:
            current.append(char)
            position += 1
            if char == '\\':
                if position >= len(source):
                    raise ValueError('Échappement incomplet dans le dump.')
                current.append(source[position])
                position += 1
            elif char == "'":
                if position < len(source) and source[position] == "'":
                    current.append("'")
                    position += 1
                else:
                    quoted = False
        elif source.startswith('/*', position):
            end = source.find('*/', position + 2)
            if end < 0:
                raise ValueError('Commentaire incomplet dans le dump.')
            comment = source[position:end + 2]
            if 'SQL_MODE=' in comment and not (
                "SQL_MODE='NO_AUTO_VALUE_ON_ZERO'" in comment
                or 'SQL_MODE=@OLD_SQL_MODE' in comment
            ):
                raise ValueError('Mode SQL source non pris en charge.')
            current.append(' ')
            position = end + 2
        elif source.startswith('--', position) or char == '#':
            end = source.find('\n', position)
            position = len(source) if end < 0 else end + 1
            current.append(' ')
        elif char == "'":
            quoted = True
            current.append(char)
            position += 1
        elif char == ';':
            statement = ''.join(current).strip()
            if statement:
                yield statement
            current = []
            position += 1
        else:
            current.append(char)
            position += 1
    if quoted or ''.join(current).strip():
        raise ValueError('Instruction source incomplète.')


TOKEN = re.compile(r"\s*(?:'((?:\\.|''|[^'\\])*)'|(NULL|-?\d+)|([(),]))", re.S)
ESCAPES = {'n': '\n', 'r': '\r', 't': '\t', '0': '\0', 'Z': '\x1a',
           'b': '\b', "'": "'", '"': '"', '\\': '\\'}


def values(source):
    tokens = []
    position = 0
    while position < len(source):
        match = TOKEN.match(source, position)
        if not match:
            if not source[position:].strip():
                break
            raise ValueError('Valeur SQL source non prise en charge.')
        raw, scalar, punctuation = match.groups()
        if raw is not None:
            value = re.sub(r"\\(.)|''", lambda m: ESCAPES.get(m[1], m[1]) if m[1] else "'", raw, flags=re.S)
            tokens.append(('value', value))
        elif scalar is not None:
            tokens.append(('value', None if scalar == 'NULL' else int(scalar)))
        else:
            tokens.append((punctuation, None))
        position = match.end()
    position = 0
    rows = []
    while position < len(tokens):
        if tokens[position][0] != '(':
            raise ValueError('Tuple SQL source attendu.')
        position += 1
        row = []
        while True:
            if position >= len(tokens) or tokens[position][0] != 'value':
                raise ValueError('Valeur source attendue.')
            row.append(tokens[position][1])
            position += 1
            if position >= len(tokens):
                raise ValueError('Tuple SQL source incomplet.')
            separator = tokens[position][0]
            position += 1
            if separator == ')':
                break
            if separator != ',':
                raise ValueError('Séparateur SQL source incorrect.')
        rows.append(row)
        if position < len(tokens):
            if tokens[position][0] != ',' or position + 1 == len(tokens):
                raise ValueError('Séparateur de tuples incorrect.')
            position += 1
    return rows


def read_dump(path):
    tables = {}
    columns = {}
    next_ids = {}
    for statement in statements(Path(path).read_text(encoding='utf-8')):
        ddl = re.fullmatch(r'CREATE TABLE `([^`]+)` \((.*)\) ENGINE=InnoDB(.*)', statement, re.S)
        insert = re.fullmatch(r'INSERT INTO `([^`]+)` VALUES\s*(.*)', statement, re.S)
        if ddl:
            name, body, options = ddl.groups()
            if name in tables or name not in SOURCE_TABLES:
                raise ValueError('Table source inconnue ou répétée.')
            columns[name] = re.findall(r'^\s*`([^`]+)`', body, re.M)
            expected = set(SOURCE_ONLY[name]) if name in SOURCE_ONLY else {
                RENAMED[name][0] if name in RENAMED and key == RENAMED[name][1] else key
                for key in HISTORICAL[name].c.keys() if key not in ADDED.get(name, ())}
            if set(columns[name]) != expected or len(set(columns[name])) != len(columns[name]):
                raise ValueError('Colonnes source incompatibles.')
            tables[name] = []
            auto = re.search(r'\bAUTO_INCREMENT=(\d+)\b', options)
            if auto:
                next_ids[name] = int(auto[1])
        elif insert:
            name, data = insert.groups()
            if name not in tables:
                raise ValueError('INSERT sans schéma source connu.')
            for row in values(data):
                if len(row) != len(columns[name]):
                    raise ValueError('Nombre de colonnes source incompatible.')
                tables[name].append(dict(zip(columns[name], row)))
        elif not re.match(r'^(CREATE DATABASE\b|USE\b|DROP TABLE IF EXISTS\b|LOCK TABLES\b|UNLOCK TABLES\b|SET\b)', statement):
            raise ValueError('Instruction source non prise en charge.')
    if set(tables) != SOURCE_TABLES:
        raise ValueError('Inventaire des tables source incompatible.')
    convert_materials(tables, next_ids)
    convert_durations(tables)
    validate(tables)
    return tables, next_ids


def convert_materials(tables, next_ids):
    """Sépare `mat_peda` en médias et outils facilitateurs (identifiants conservés).

    Un outil est une ligne dont le type relève de `ref.type_outil`. `localisation` et, pour les médias,
    `variante`, `difficulte_id`, `materiel` et `fk_type_mat_outil_id` ne sont pas repris. Les liaisons
    avec séquences et thématiques ne concernent que des médias : une liaison sur un outil est refusée.
    """
    families = {row['id']: row['reference'] for row in tables['thesaurus']}
    tables['media'], tables['outil_facilitateur'] = [], []
    tool_ids = set()
    for row in tables.pop('mat_peda'):
        if families.get(row['fk_type_mat_id']) == 'ref.type_outil':
            tool_ids.add(row['id'])
            tables['outil_facilitateur'].append({
                'id': row['id'], 'fk_type_outil_id': row['fk_type_mat_id'], 'nom': row['nom'],
                'description': row['description'], 'url': row['url'], 'variante': row['variante'],
                'difficulte_id': row['difficulte_id'], 'materiel': row['materiel'],
                'date_modif': row['date_modif'], 'fk_type_mat_outil_id': row['fk_type_mat_outil_id']})
        else:
            tables['media'].append({key: row[key] for key in ('id', 'fk_type_mat_id', 'nom', 'description', 'url', 'date_modif')})
    for old, new in (('rel_mat_peda_sequence', 'rel_media_sequence'), ('rel_mat_peda_thematique', 'rel_media_thematique')):
        rows = tables.pop(old)
        if any(row['fk_mat_peda_id'] in tool_ids for row in rows):
            raise ValueError('Liaison source sur un outil facilitateur : import refusé.')
        tables[new] = [{('fk_media_id' if key == 'fk_mat_peda_id' else key): value for key, value in row.items()} for row in rows]
        if old in next_ids:
            next_ids[new] = next_ids.pop(old)
    if 'mat_peda' in next_ids:
        next_ids['media'] = next_ids['outil_facilitateur'] = next_ids.pop('mat_peda')


def convert_durations(tables):
    """Remplace la référence de durée des séquences ('5 min', '1h30'…) par un nombre de minutes."""
    labels = {row['id']: row['label'] for row in tables['thesaurus']}
    for row in tables['sequence']:
        label = (labels.get(row.pop('fk_duree_id')) or '').lower()
        hours = re.fullmatch(r'\s*(\d+)\s*h\s*(\d+)?\s*', label)
        short = re.fullmatch(r'\s*(\d+)\s*min\s*', label)
        row['duree_minutes'] = (int(hours[1]) * 60 + int(hours[2] or 0)) if hours else int(short[1]) if short else 0
    # Position initiale des termes : ordre alphabétique au sein de chaque référence.
    ranks = {}
    for row in sorted(tables['thesaurus'], key=lambda r: (r['reference'] or '', r['label'] or '', r['id'])):
        row['position'] = ranks[row['reference'] or ''] = ranks.get(row['reference'] or '', -1) + 1
    # La famille ref.duree_seq n'existe plus dans le thésaurus (migration 0005).
    removed = {row['id'] for row in tables['thesaurus'] if 'ref.duree_seq' in (row['reference'], row['code'])}
    tables['thesaurus'][:] = [row for row in tables['thesaurus'] if row['id'] not in removed]
    for name, column in (('rel_anim_tag', 'fk_thes_id'), ('rel_media_thematique', 'fk_thes_id')):
        tables[name][:] = [row for row in tables[name] if row[column] not in removed]


def validate(tables):
    for table in HISTORICAL_SORTED:
        rows = tables[table.name]
        for row in rows:
            for column in table.c:
                value = row[column.name]
                if value is None:
                    if not column.nullable:
                        raise ValueError('NULL source incompatible.')
                    continue
                if isinstance(column.type, Integer):
                    if type(value) is not int or not -(2**31) <= value < 2**31:
                        raise ValueError('Entier source incompatible.')
                elif isinstance(column.type, Date):
                    try:
                        row[column.name] = date.fromisoformat(value)
                    except (TypeError, ValueError):
                        raise ValueError('Date source incompatible.') from None
                elif isinstance(column.type, String):
                    if not isinstance(value, str) or '\0' in value or (column.type.length and len(value) > column.type.length):
                        raise ValueError('Texte source incompatible.')
                for fk in column.foreign_keys:
                    if value not in {r[fk.column.name] for r in tables[fk.column.table.name]}:
                        raise ValueError('Référence source orpheline.')
        unique_columns = [('id',)] + [tuple(c.name for c in constraint.columns)
                                    for constraint in table.constraints
                                    if isinstance(constraint, UniqueConstraint)]
        for names in unique_columns:
            keys = [tuple(row[name] for name in names) for row in rows
                    if all(row[name] is not None for name in names)]
            if len(set(keys)) != len(keys):
                raise ValueError('Clé source dupliquée.')


def restore(connection, tables, next_ids):
    """Appeler dans une transaction ; verrouiller avant le contrôle de vacuité."""
    metadata = Base.metadata
    connection.execute(text("SET LOCAL search_path TO public"))
    connection.execute(text("SET LOCAL lock_timeout = '10s'"))
    names = ', '.join('public.' + connection.dialect.identifier_preparer.quote(t.name)
                      for t in metadata.sorted_tables)
    connection.exec_driver_sql(f'LOCK TABLE {names} IN ACCESS EXCLUSIVE MODE')
    if set(inspect(connection).get_table_names(schema='public')) != set(metadata.tables) | {'alembic_version'}:
        raise ValueError('Inventaire cible incompatible.')
    # Le schéma doit être à jour : l'import ne se fait pas sur une base en retard sur les migrations.
    if sorted(connection.execute(text('SELECT version_num FROM alembic_version')).scalars().all()) != head_revisions():
        raise ValueError('Révision Alembic cible incompatible.')
    context = MigrationContext.configure(connection, opts={'compare_type': True, 'compare_server_default': True})
    if compare_metadata(context, metadata):
        raise ValueError('Schéma cible différent des modèles ; import refusé.')
    if any(connection.execute(select(table.c.id).limit(1)).first() is not None
           for table in HISTORICAL_SORTED):
        print('Base déjà alimentée : aucune restauration effectuée.')
        return False
    for table in HISTORICAL_SORTED:
        rows = tables[table.name]
        if rows:
            connection.execute(table.insert(), rows)
        actual = {row['id']: dict(row) for row in connection.execute(select(table)).mappings()}
        if actual != {row['id']: row for row in rows}:
            raise ValueError('Vérification des données importées échouée.')
    # ALTER SEQUENCE RESTART est transactionnel contrairement à setval().
    for table in HISTORICAL_SORTED:
        if not isinstance(table.c.id.type, Integer):
            continue
        next_id = max(1, next_ids.get(table.name, 1),
                      max((row['id'] for row in tables[table.name]), default=0) + 1)
        if next_id > 2**31 - 1:
            raise ValueError('Séquence source hors limites.')
        sequence = connection.execute(text('SELECT pg_get_serial_sequence(:table, :column)'),
                                      {'table': 'public.' + table.name, 'column': 'id'}).scalar_one()
        if not sequence:
            raise ValueError('Séquence cible absente.')
        # pg_get_serial_sequence renvoie un identifiant qualifié déjà échappé par PostgreSQL.
        connection.exec_driver_sql(f'ALTER SEQUENCE {sequence} RESTART WITH {next_id}')
    return True
