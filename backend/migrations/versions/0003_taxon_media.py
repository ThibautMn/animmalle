"""Table des taxons TaxHub possédant au moins un média (bibliothèque du PNC).

Revision ID: 0003_taxon_media
Revises: 0002_index_recherche
"""
from alembic import op
import sqlalchemy as sa

revision = '0003_taxon_media'
down_revision = '0002_index_recherche'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('taxon_media',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('cd_ref', sa.Integer(), nullable=False),
    sa.Column('lb_nom', sa.String(length=250), nullable=False),
    sa.Column('nom_vern', sa.Text(), nullable=True),
    sa.Column('nom_valide', sa.Text(), nullable=True),
    sa.Column('group2_inpn', sa.String(length=100), nullable=True),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_taxon_media')),
    sa.UniqueConstraint('cd_ref', name=op.f('uq_taxon_media_cd_ref'))
    )


def downgrade():
    op.drop_table('taxon_media')
