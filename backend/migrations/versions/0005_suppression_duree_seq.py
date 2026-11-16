"""Suppression de la famille ref.duree_seq du thésaurus, remplacée par duree_minutes.

Revision ID: 0005_suppr_duree_seq
Revises: 0004_duree_minutes
"""
from alembic import op

revision = '0005_suppr_duree_seq'
down_revision = '0004_duree_minutes'
branch_labels = None
depends_on = None

# Valeurs de la famille et ligne d'en-tête (reference vide, code = nom de la famille).
CONDITION = "(reference = 'ref.duree_seq' OR code = 'ref.duree_seq')"


def upgrade():
    # Par précaution, retirer les éventuelles associations avant les valeurs elles-mêmes.
    for table in ('rel_anim_tag', 'rel_mat_peda_thematique'):
        op.execute(f'DELETE FROM {table} WHERE fk_thes_id IN (SELECT id FROM thesaurus WHERE {CONDITION})')
    op.execute(f'DELETE FROM thesaurus WHERE {CONDITION}')


def downgrade():
    raise NotImplementedError('Les valeurs supprimées du thésaurus ne sont pas restaurées.')
