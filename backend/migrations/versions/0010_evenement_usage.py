"""Table des événements d'usage (connexions, consultations, téléchargements).

Revision ID: 0010_evenement_usage
Revises: 0009_index_media_outil
"""
from alembic import op
import sqlalchemy as sa

revision = '0010_evenement_usage'
down_revision = '0009_index_media_outil'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'evenement_usage',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('date', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.Column('type', sa.String(length=20), nullable=False),
        sa.Column('ressource', sa.String(length=20), nullable=True),
        sa.Column('ressource_id', sa.String(length=40), nullable=True),
        sa.PrimaryKeyConstraint('id', name='pk_evenement_usage'),
    )
    op.create_index('ix_evenement_usage_date', 'evenement_usage', ['date'])


def downgrade():
    op.drop_index('ix_evenement_usage_date', table_name='evenement_usage')
    op.drop_table('evenement_usage')
