"""Durée des séquences en minutes (entier) au lieu d'une référence du thésaurus.

Revision ID: 0004_duree_minutes
Revises: 0003_taxon_media
"""
from alembic import op
import sqlalchemy as sa

revision = '0004_duree_minutes'
down_revision = '0003_taxon_media'
branch_labels = None
depends_on = None


DUREES = {
    '5 min': 5, '10 min': 10, '15 min': 15, '20 min': 20, '25 min': 25, '30 min': 30,
    '35 min': 35, '40 min': 40, '45 min': 45, '50 min': 50, '55 min': 55,
    '1h': 60, '1h30': 90, '2h': 120,
}


def upgrade():
    op.add_column('sequence', sa.Column('duree_minutes', sa.Integer(), nullable=True))
    # Libellés de la famille ref.duree_seq du thésaurus -> minutes ; 0 si le libellé est inconnu.
    cases = ' '.join(f"WHEN '{label}' THEN {value}" for label, value in DUREES.items())
    op.execute(
        "UPDATE sequence SET duree_minutes = COALESCE((SELECT CASE t.label " + cases + " END "
        "FROM thesaurus t WHERE t.id = sequence.fk_duree_id AND t.reference = 'ref.duree_seq'), 0)")
    op.alter_column('sequence', 'duree_minutes', existing_type=sa.Integer(), nullable=False)
    op.drop_index('ix_sequence_fk_duree_id', table_name='sequence')
    op.drop_constraint('fk_sequence_fk_duree_id_thesaurus', 'sequence', type_='foreignkey')
    op.drop_column('sequence', 'fk_duree_id')


def downgrade():
    raise NotImplementedError('Les durées en minutes ne se convertissent pas en références du thésaurus.')
