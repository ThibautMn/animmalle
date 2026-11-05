"""Reprise de données MariaDB : aucun ordre SQL source n'est exécuté."""

from datetime import date
from pathlib import Path
import re

from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import Date, Integer, String, UniqueConstraint, inspect, select, text
from animmalle.models import Base


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
            if name in tables or name not in Base.metadata.tables:
                raise ValueError('Table source inconnue ou répétée.')
            columns[name] = re.findall(r'^\s*`([^`]+)`', body, re.M)
            if set(columns[name]) != set(Base.metadata.tables[name].c.keys()) or len(set(columns[name])) != len(columns[name]):
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
    if set(tables) != set(Base.metadata.tables):
        raise ValueError('Inventaire des tables source incompatible.')
    validate(tables)
    return tables, next_ids


def validate(tables):
    for table in Base.metadata.sorted_tables:
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
    if connection.execute(text('SELECT version_num FROM alembic_version')).scalars().all() != ['0001_initial']:
        raise ValueError('Révision Alembic cible incompatible.')
    context = MigrationContext.configure(connection, opts={'compare_type': True, 'compare_server_default': True})
    if compare_metadata(context, metadata):
        raise ValueError('Schéma cible différent des modèles ; import refusé.')
    if any(connection.execute(select(table.c.id).limit(1)).first() is not None
           for table in metadata.sorted_tables):
        print('Base déjà alimentée : aucune restauration effectuée.')
        return False
    for table in metadata.sorted_tables:
        rows = tables[table.name]
        if rows:
            connection.execute(table.insert(), rows)
        actual = {row['id']: dict(row) for row in connection.execute(select(table)).mappings()}
        if actual != {row['id']: row for row in rows}:
            raise ValueError('Vérification des données importées échouée.')
    # ALTER SEQUENCE RESTART est transactionnel contrairement à setval().
    for table in metadata.sorted_tables:
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
