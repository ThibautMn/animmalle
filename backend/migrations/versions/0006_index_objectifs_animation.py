"""Index trigramme sur les objectifs des animations (recherche textuelle, PostgreSQL).

Revision ID: 0006_index_objectifs
Revises: 0005_suppr_duree_seq
"""
from alembic import op

revision = '0006_index_objectifs'
down_revision = '0005_suppr_duree_seq'
branch_labels = None
depends_on = None


def upgrade():
    if op.get_bind().dialect.name != 'postgresql':
        return
    op.execute('CREATE EXTENSION IF NOT EXISTS pg_trgm')
    op.execute('CREATE INDEX ix_animation_objectifs_trgm ON animation USING gin (objectifs gin_trgm_ops)')


def downgrade():
    if op.get_bind().dialect.name != 'postgresql':
        return
    op.execute('DROP INDEX IF EXISTS ix_animation_objectifs_trgm')
