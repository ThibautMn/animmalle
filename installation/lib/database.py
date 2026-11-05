"""Phases explicites de préparation PostgreSQL ; jamais exécutées à l'import."""

from pathlib import Path
import os
import stat
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'backend'))


def provision_local_database(url):
    """Créer seulement les objets absents via le compte administrateur local."""
    from psycopg import sql

    role = sql.Literal(url.username).as_string()
    password = sql.Literal(url.password).as_string()
    database = sql.Literal(url.database).as_string()
    # Les valeurs sont des littéraux SQL échappés ; format(%I/%L) construit
    # ensuite les commandes. Le secret transite par stdin, jamais par argv.
    statements = f"""
SELECT pg_advisory_lock(173528, 3);
SELECT format('CREATE ROLE %I LOGIN PASSWORD %L', {role}, {password})
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = {role})
\u005cgexec
SELECT format('CREATE DATABASE %I OWNER %I', {database}, {role})
WHERE NOT EXISTS (SELECT 1 FROM pg_database WHERE datname = {database})
\u005cgexec
"""
    result = subprocess.run(
        ['sudo', '-u', 'postgres', 'psql', '-X', '--no-password',
         '--host=/var/run/postgresql', f'--port={url.port}', '--dbname=postgres',
         '--set=ON_ERROR_STOP=1', '--quiet'],
        input=statements, capture_output=True, text=True,
    )
    if result.returncode:
        raise ValueError('Échec de préparation du rôle ou de la base ; vérifier le compte postgres, le socket local et les droits sudo. Détails masqués pour protéger les secrets.')
    print('Rôle et base PostgreSQL disponibles ; objets existants conservés.')


def run(phase):
    from sqlalchemy import create_engine, inspect, text
    from animmalle.config import CONFIG_PATH, load_database_url

    if not CONFIG_PATH.is_file():
        raise ValueError('Créer installation/config_principal.yaml depuis le modèle et protéger ses permissions (600).')
    permissions = CONFIG_PATH.stat()
    if permissions.st_uid != os.getuid() or stat.S_IMODE(permissions.st_mode) & 0o077:
        raise ValueError('Le YAML doit appartenir au compte courant et avoir les permissions 600 ou 400.')
    url = load_database_url()
    if url.password == 'REMPLACER':
        raise ValueError('Renseigner le mot de passe PostgreSQL dans le YAML.')
    if url.database in {'postgres', 'template0', 'template1'}:
        raise ValueError('Choisir une base applicative distincte des bases système.')

    if phase == 'restore':
        dump = ROOT / 'installation/dump_bdd/bdd.dump'
        if not dump.exists():
            print('Dump absent : aucune restauration effectuée.')
            return
        from restore import read_dump, restore

        tables, next_ids = read_dump(dump)
        engine = create_engine(url, hide_parameters=True)
        try:
            with engine.begin() as connection:
                imported = restore(connection, tables, next_ids)
            if imported:
                for name, rows in sorted(tables.items()):
                    print(f'{name} : {len(rows)} lignes restaurées et vérifiées.')
                print('Import validé et transaction enregistrée ; séquences recalées.')
        finally:
            engine.dispose()
        return

    local = url.host in {'localhost', '127.0.0.1', '::1'} and url.port == 5432
    if local:
        print('Démarrage du service PostgreSQL local.', flush=True)
        result = subprocess.run(['sudo', 'systemctl', 'start', 'postgresql'], check=False)
        if result.returncode:
            raise ValueError('Impossible de démarrer PostgreSQL local ; vérifier le service et le cluster.')
        provision_local_database(url)

    else:
        admin = create_engine(url.set(database='postgres'), isolation_level='AUTOCOMMIT')
        try:
            with admin.connect() as connection:
                exists = connection.execute(
                    text('SELECT 1 FROM pg_database WHERE datname = :name'),
                    {'name': url.database},
                ).scalar()
                if not exists:
                    quoted = connection.dialect.identifier_preparer.quote_identifier(url.database)
                    connection.exec_driver_sql(f'CREATE DATABASE {quoted}')
                    print('Base applicative créée.')
        finally:
            admin.dispose()

    engine = create_engine(url)
    try:
        with engine.connect() as connection:
            tables = inspect(connection).get_table_names(schema='public')
            if tables and 'alembic_version' not in tables:
                raise ValueError('Base contenant un schéma non géré par Alembic : intervention nécessaire.')
    finally:
        engine.dispose()
    # Capturer les erreurs pour ne pas exposer les paramètres ou les secrets SQL.
    result = subprocess.run(
        [sys.executable, '-m', 'alembic', '-c', str(ROOT / 'backend/alembic.ini'),
         'upgrade', 'head'], cwd=ROOT, capture_output=True, text=True,
    )
    if result.returncode:
        raise ValueError('Échec des migrations Alembic ; détails masqués pour protéger les secrets. Vérifier la configuration et les droits.')
    print('Schéma Alembic à jour. Aucune donnée restaurée.')


if __name__ == '__main__':
    try:
        if len(sys.argv) != 2 or sys.argv[1] not in {'schema', 'restore'}:
            raise ValueError('Phase attendue : schema ou restore.')
        run(sys.argv[1])
    except Exception as error:
        # Les messages externes (pilote, OS, SQL) peuvent contenir des secrets.
        message = str(error) if type(error) is ValueError else 'Opération impossible : vérifier prérequis, connexion et droits PostgreSQL.'
        print(message, file=sys.stderr)
        sys.exit(1)
