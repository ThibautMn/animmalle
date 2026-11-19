"""Phases explicites de préparation PostgreSQL ; jamais exécutées à l'import."""

from pathlib import Path
import os
import stat
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'backend'))


def provision_local_database(url):
    """Créer les objets absents via le compte administrateur local.

    Le YAML fait foi pour le mot de passe : un rôle existant y est resynchronisé."""
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
SELECT format('ALTER ROLE %I LOGIN PASSWORD %L', {role}, {password})
\u005cgexec
SELECT format('CREATE DATABASE %I OWNER %I ENCODING ''UTF8'' LC_COLLATE ''C.UTF-8'' LC_CTYPE ''C.UTF-8'' TEMPLATE template0', {database}, {role})
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
    print('Rôle (mot de passe aligné sur le YAML) et base PostgreSQL disponibles ; aucune donnée modifiée.')


def _local_psql(url, query, dbname='postgres'):
    result = subprocess.run(
        ['sudo', '-u', 'postgres', 'psql', '-X', '--no-password', '-At',
         '--host=/var/run/postgresql', f'--port={url.port}', f'--dbname={dbname}',
         f'--set=db={url.database}', '--set=ON_ERROR_STOP=1', '--quiet'],
        input=query, capture_output=True, text=True,
    )
    if result.returncode:
        raise ValueError('Échec de la vérification de la base PostgreSQL locale. Détails masqués.')
    return result.stdout.strip()


def ensure_utf8_database(url):
    """Une base SQL_ASCII fait renvoyer des octets par psycopg : la recréer si elle est vide."""
    encoding = _local_psql(url, "SELECT pg_encoding_to_char(encoding) FROM pg_database WHERE datname = :'db';")
    if not encoding or encoding == 'UTF8':
        return
    tables = _local_psql(
        url, "SELECT count(*) FROM pg_tables WHERE schemaname NOT IN ('pg_catalog', 'information_schema');",
        dbname=url.database)
    if tables != '0':
        raise ValueError(f'La base existe en encodage {encoding} et contient des tables : la convertir en UTF8 manuellement (pg_dump puis recréation).')
    _local_psql(url, "SELECT format('DROP DATABASE %I', :'db') \\gexec")
    print(f'Base vide en encodage {encoding} supprimée ; elle sera recréée en UTF8.')


def run(phase):
    from sqlalchemy import create_engine, inspect, text
    from sqlalchemy.exc import OperationalError
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
        ensure_utf8_database(url)
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

    engine = create_engine(url, hide_parameters=True)
    try:
        try:
            connection = engine.connect()
        except OperationalError:
            raise ValueError('Connexion à la base refusée avec les identifiants du YAML. Vérifier postgresql.host, port, username et password, et pg_hba.conf si le serveur n’est pas local.') from None
        with connection:
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
        if type(error) is not ValueError:
            # Le type d'exception ne contient ni paramètre ni secret.
            print(f'Type d’erreur : {type(error).__module__}.{type(error).__name__}', file=sys.stderr)
            # Seulement fichier, ligne et code source des appels : ni valeurs ni message.
            import traceback
            for frame in traceback.extract_tb(error.__traceback__):
                print(f'  {frame.filename}:{frame.lineno} {frame.name} : {frame.line}', file=sys.stderr)
        sys.exit(1)
