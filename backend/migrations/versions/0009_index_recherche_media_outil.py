"""Index trigramme pour la recherche textuelle des médias et des outils facilitateurs (PostgreSQL).

Revision ID: 0009_index_media_outil
Revises: 0008_separation_media_outil
"""
from alembic import op

revision = '0009_index_media_outil'
down_revision = '0008_separation_media_outil'
branch_labels = None
depends_on = None

INDEXES = {
    'media': ('nom', 'description'),
    'outil_facilitateur': ('nom', 'description', 'variante', 'materiel'),
}


def upgrade():
    if op.get_bind().dialect.name != 'postgresql':
        return
    op.execute('CREATE EXTENSION IF NOT EXISTS pg_trgm')
    for table, columns in INDEXES.items():
        for column in columns:
            op.execute(f'CREATE INDEX ix_{table}_{column}_trgm ON {table} USING gin ({column} gin_trgm_ops)')


def downgrade():
    if op.get_bind().dialect.name != 'postgresql':
        return
    for table, columns in INDEXES.items():
        for column in columns:
            op.execute(f'DROP INDEX IF EXISTS ix_{table}_{column}_trgm')
