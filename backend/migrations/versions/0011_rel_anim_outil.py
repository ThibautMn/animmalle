"""Outils facilitateurs ajoutés aux animations (remplacée par la révision 0012).

Revision ID: 0011_rel_anim_outil
Revises: 0010_evenement_usage
"""
from alembic import op
import sqlalchemy as sa

revision = '0011_rel_anim_outil'
down_revision = '0010_evenement_usage'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'rel_anim_outil',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('fk_anim_id', sa.String(length=40), nullable=False),
        sa.Column('fk_outil_id', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['fk_anim_id'], ['animation.id'], name='fk_rel_anim_outil_fk_anim_id_animation'),
        sa.ForeignKeyConstraint(['fk_outil_id'], ['outil_facilitateur.id'], name='fk_rel_anim_outil_fk_outil_id_outil_facilitateur'),
        sa.PrimaryKeyConstraint('id', name='pk_rel_anim_outil'),
        sa.UniqueConstraint('fk_anim_id', 'fk_outil_id', name='uq_rel_anim_outil_pair'),
    )
    op.create_index('ix_rel_anim_outil_fk_anim_id', 'rel_anim_outil', ['fk_anim_id'])
    op.create_index('ix_rel_anim_outil_fk_outil_id', 'rel_anim_outil', ['fk_outil_id'])


def downgrade():
    op.drop_index('ix_rel_anim_outil_fk_outil_id', table_name='rel_anim_outil')
    op.drop_index('ix_rel_anim_outil_fk_anim_id', table_name='rel_anim_outil')
    op.drop_table('rel_anim_outil')
