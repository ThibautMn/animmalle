"""Position des termes du thésaurus (ordre d'affichage modifiable).

Revision ID: 0007_position_thesaurus
Revises: 0006_index_objectifs
"""
from alembic import op
import sqlalchemy as sa

revision = '0007_position_thesaurus'
down_revision = '0006_index_objectifs'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('thesaurus', sa.Column('position', sa.Integer(), server_default=sa.text('0'), nullable=False))
    # Ordre initial = ordre alphabétique actuel, au sein de chaque référence.
    op.execute(
        'UPDATE thesaurus SET position = ranked.rang FROM ('
        'SELECT id, ROW_NUMBER() OVER (PARTITION BY reference ORDER BY label, id) - 1 AS rang FROM thesaurus'
        ') AS ranked WHERE thesaurus.id = ranked.id'
    )


def downgrade():
    op.drop_column('thesaurus', 'position')
