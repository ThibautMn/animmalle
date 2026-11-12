"""Index trigramme pour la recherche textuelle des animations (PostgreSQL).

Revision ID: 0002_index_recherche
Revises: 0001_initial
"""
from alembic import op

revision = '0002_index_recherche'
down_revision = '0001_initial'
branch_labels = None
depends_on = None


def upgrade():
    if op.get_bind().dialect.name != 'postgresql':
        return
    op.execute('CREATE EXTENSION IF NOT EXISTS pg_trgm')
    op.execute('CREATE INDEX ix_animation_titre_trgm ON animation USING gin (titre gin_trgm_ops)')
    op.execute('CREATE INDEX ix_animation_description_trgm ON animation USING gin (description gin_trgm_ops)')


def downgrade():
    if op.get_bind().dialect.name != 'postgresql':
        return
    op.execute('DROP INDEX IF EXISTS ix_animation_description_trgm')
    op.execute('DROP INDEX IF EXISTS ix_animation_titre_trgm')
