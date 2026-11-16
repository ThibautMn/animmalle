"""Audit en lecture seule du format SQL MariaDB fourni, sans exécution SQL.

Cet outil ne convertit ni ne restaure les données. Les sorties sont des agrégats.
"""

from collections import Counter
from datetime import date
from pathlib import Path
import re

DUMP_PATH = Path(__file__).resolve().parents[2] / 'installation/dump_bdd/bdd.dump'


def read_dump(path=DUMP_PATH):
    sql = Path(path).read_text(encoding='utf-8')
    schemas = {
        match[1]: re.findall(r'^  `([^`]+)`', match[2], re.M)
        for match in re.finditer(r'CREATE TABLE `([^`]+)` \((.*?)\n\)', sql, re.S)
    }
    tables = {name: [] for name in schemas}
    for match in re.finditer(r'INSERT INTO `([^`]+)` VALUES\s*', sql):
        position = match.end()
        while sql[position] == '(':
            position += 1
            row = []
            while True:
                if sql[position] == "'":
                    position += 1
                    value = ''
                    while True:
                        char = sql[position]
                        position += 1
                        if char == '\\':
                            char = sql[position]
                            value += {'n': '\n', 'r': '\r', 't': '\t',
                                      '0': '\0', 'Z': '\x1a'}.get(char, char)
                            position += 1
                        elif char == "'":
                            if sql[position] == "'":
                                value += "'"
                                position += 1
                            else:
                                break
                        else:
                            value += char
                else:
                    end = position
                    while sql[end] not in ',)':
                        end += 1
                    token = sql[position:end]
                    value = None if token == 'NULL' else int(token)
                    position = end
                row.append(value)
                separator = sql[position]
                position += 1
                if separator == ')':
                    break
                if separator != ',':
                    raise ValueError('Format INSERT non pris en charge.')
            if len(row) != len(schemas[match[1]]):
                raise ValueError('Nombre de colonnes incompatible.')
            tables[match[1]].append(dict(zip(schemas[match[1]], row)))
            if sql[position] == ';':
                break
            if sql[position] != ',':
                raise ValueError('Format INSERT non pris en charge.')
            position += 1
            while sql[position].isspace():
                position += 1
    return tables


def audit(path=DUMP_PATH):
    tables = read_dump(path)
    for name, rows in tables.items():
        nulls = {key: sum(row[key] is None for row in rows)
                 for key in rows[0] if any(row[key] is None for row in rows)} if rows else {}
        maximum = max((row['id'] for row in rows), default=None)
        print(name, 'lignes', len(rows), 'max_id', maximum, 'nulls', nulls)
        for column in (key for key in rows[0] if key.endswith('_id')) if rows else ():
            if column in ('fk_anim_id', 'fk_id_anim_id'):
                target = 'animation'
            elif column == 'fk_mat_peda_id':
                target = 'mat_peda'
            elif column == 'fk_sequence_id':
                target = 'sequence'
            else:
                target = 'thesaurus'
            ids = {row['id'] for row in tables[target]}
            orphans = sum(row[column] is not None and row[column] not in ids for row in rows)
            print(' ', column, 'orphelins', orphans)
            if orphans:
                raise ValueError('Référence orpheline détectée.')
        if name.startswith('rel_') and rows:
            columns = [key for key in rows[0] if key != 'id']
            counts = Counter(tuple(row[key] for key in columns) for row in rows)
            duplicates = sum(count - 1 for count in counts.values())
            print('  doublons_couples', duplicates)
            if duplicates:
                raise ValueError('Couple de liaison dupliqué.')
    print('statuts', dict(Counter(row['statut'] for row in tables['animation'])))
    print('codes_vides', sum(row['code'] == '' for row in tables['thesaurus']))
    return tables


def validate_models(tables):
    # Import facultatif : exécuter avec PYTHONPATH=backend et les dépendances installées.
    from sqlalchemy import Date, String
    from animmalle.models import APPLICATION_TABLES, Base

    if set(tables) != set(Base.metadata.tables) - APPLICATION_TABLES:
        raise ValueError('Tables incompatibles.')
    for name, rows in tables.items():
        table = Base.metadata.tables[name]
        for row in rows:
            if set(row) != set(table.c.keys()):
                raise ValueError('Colonnes incompatibles.')
            for column in table.c:
                value = row[column.name]
                if value is None and not column.nullable:
                    raise ValueError('NULL incompatible.')
                if value is not None and isinstance(column.type, String) and column.type.length:
                    if len(value) > column.type.length:
                        raise ValueError('Longueur incompatible.')
                if value is not None and isinstance(column.type, Date):
                    date.fromisoformat(value)
    print('Colonnes, nullabilité, longueurs et dates compatibles avec les modèles.')


if __name__ == '__main__':
    import sys
    result = audit()
    if '--models' in sys.argv[1:]:
        validate_models(result)
