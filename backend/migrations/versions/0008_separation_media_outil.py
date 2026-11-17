"""Sépare `mat_peda` en `media` et `outil_facilitateur`.

Les lignes dont le type appartient à `ref.type_outil` deviennent des outils, toutes les autres
des médias. Les identifiants sont conservés. Les colonnes `localisation` (toujours vide),
`variante`, `difficulte_id`, `materiel` et `fk_type_mat_outil_id` ne subsistent pas sur `media`.

Revision ID: 0008_separation_media_outil
Revises: 0007_position_thesaurus
"""
from alembic import op
import sqlalchemy as sa

revision = '0008_separation_media_outil'
down_revision = '0007_position_thesaurus'
branch_labels = None
depends_on = None

IS_TOOL = "EXISTS (SELECT 1 FROM thesaurus t WHERE t.id = mat_peda.fk_type_mat_id AND t.reference = 'ref.type_outil')"


def recalage(table):
    op.execute(
        f"SELECT setval(pg_get_serial_sequence('{table}', 'id'), COALESCE((SELECT MAX(id) FROM {table}), 1), "
        f"(SELECT COUNT(*) > 0 FROM {table}))")


def upgrade():
    op.create_table('media',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('fk_type_mat_id', sa.Integer(), nullable=False),
    sa.Column('nom', sa.String(length=100), nullable=False),
    sa.Column('description', sa.Text(), nullable=False),
    sa.Column('url', sa.String(length=250), nullable=False),
    sa.Column('date_modif', sa.Date(), server_default=sa.text('CURRENT_DATE'), nullable=True),
    sa.ForeignKeyConstraint(['fk_type_mat_id'], ['thesaurus.id'], name=op.f('fk_media_fk_type_mat_id_thesaurus')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_media'))
    )
    op.create_index(op.f('ix_media_fk_type_mat_id'), 'media', ['fk_type_mat_id'], unique=False)
    op.create_table('outil_facilitateur',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('fk_type_outil_id', sa.Integer(), nullable=False),
    sa.Column('nom', sa.String(length=100), nullable=False),
    sa.Column('description', sa.Text(), nullable=False),
    sa.Column('url', sa.String(length=250), nullable=False),
    sa.Column('variante', sa.Text(), nullable=False),
    sa.Column('difficulte_id', sa.Integer(), nullable=True),
    sa.Column('materiel', sa.Text(), nullable=False),
    sa.Column('date_modif', sa.Date(), server_default=sa.text('CURRENT_DATE'), nullable=True),
    sa.Column('fk_type_mat_outil_id', sa.Integer(), nullable=True),
    sa.ForeignKeyConstraint(['difficulte_id'], ['thesaurus.id'], name=op.f('fk_outil_facilitateur_difficulte_id_thesaurus')),
    sa.ForeignKeyConstraint(['fk_type_mat_outil_id'], ['thesaurus.id'], name=op.f('fk_outil_facilitateur_fk_type_mat_outil_id_thesaurus')),
    sa.ForeignKeyConstraint(['fk_type_outil_id'], ['thesaurus.id'], name=op.f('fk_outil_facilitateur_fk_type_outil_id_thesaurus')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_outil_facilitateur'))
    )
    op.create_index(op.f('ix_outil_facilitateur_difficulte_id'), 'outil_facilitateur', ['difficulte_id'], unique=False)
    op.create_index(op.f('ix_outil_facilitateur_fk_type_mat_outil_id'), 'outil_facilitateur', ['fk_type_mat_outil_id'], unique=False)
    op.create_index(op.f('ix_outil_facilitateur_fk_type_outil_id'), 'outil_facilitateur', ['fk_type_outil_id'], unique=False)
    op.create_table('rel_media_sequence',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('fk_media_id', sa.Integer(), nullable=False),
    sa.Column('fk_sequence_id', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['fk_media_id'], ['media.id'], name=op.f('fk_rel_media_sequence_fk_media_id_media')),
    sa.ForeignKeyConstraint(['fk_sequence_id'], ['sequence.id'], name=op.f('fk_rel_media_sequence_fk_sequence_id_sequence')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_rel_media_sequence')),
    sa.UniqueConstraint('fk_media_id', 'fk_sequence_id', name='uq_rel_media_sequence_pair')
    )
    op.create_index(op.f('ix_rel_media_sequence_fk_media_id'), 'rel_media_sequence', ['fk_media_id'], unique=False)
    op.create_index(op.f('ix_rel_media_sequence_fk_sequence_id'), 'rel_media_sequence', ['fk_sequence_id'], unique=False)
    op.create_table('rel_media_thematique',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('fk_media_id', sa.Integer(), nullable=False),
    sa.Column('fk_thes_id', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['fk_media_id'], ['media.id'], name=op.f('fk_rel_media_thematique_fk_media_id_media')),
    sa.ForeignKeyConstraint(['fk_thes_id'], ['thesaurus.id'], name=op.f('fk_rel_media_thematique_fk_thes_id_thesaurus')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_rel_media_thematique')),
    sa.UniqueConstraint('fk_media_id', 'fk_thes_id', name='uq_rel_media_thematique_pair')
    )
    op.create_index(op.f('ix_rel_media_thematique_fk_media_id'), 'rel_media_thematique', ['fk_media_id'], unique=False)
    op.create_index(op.f('ix_rel_media_thematique_fk_thes_id'), 'rel_media_thematique', ['fk_thes_id'], unique=False)

    op.execute(
        'INSERT INTO media (id, fk_type_mat_id, nom, description, url, date_modif) '
        f'SELECT id, fk_type_mat_id, nom, description, url, date_modif FROM mat_peda WHERE NOT {IS_TOOL}')
    op.execute(
        'INSERT INTO outil_facilitateur (id, fk_type_outil_id, nom, description, url, variante, difficulte_id, '
        'materiel, date_modif, fk_type_mat_outil_id) '
        'SELECT id, fk_type_mat_id, nom, description, url, variante, difficulte_id, materiel, date_modif, '
        f'fk_type_mat_outil_id FROM mat_peda WHERE {IS_TOOL}')
    # Les outils n'ont ni séquence ni thématique ; une liaison d'outil existante est refusée plutôt que perdue.
    for table in ('rel_mat_peda_sequence', 'rel_mat_peda_thematique'):
        op.execute(
            f'DO $$ BEGIN IF EXISTS (SELECT 1 FROM {table} r JOIN outil_facilitateur o ON o.id = r.fk_mat_peda_id) '
            f"THEN RAISE EXCEPTION 'Liaison {table} sur un outil facilitateur : migration refusée'; END IF; END $$")
    op.execute('INSERT INTO rel_media_sequence (id, fk_media_id, fk_sequence_id) '
               'SELECT id, fk_mat_peda_id, fk_sequence_id FROM rel_mat_peda_sequence')
    op.execute('INSERT INTO rel_media_thematique (id, fk_media_id, fk_thes_id) '
               'SELECT id, fk_mat_peda_id, fk_thes_id FROM rel_mat_peda_thematique')
    for table in ('media', 'outil_facilitateur', 'rel_media_sequence', 'rel_media_thematique'):
        recalage(table)

    for table in ('rel_mat_peda_thematique', 'rel_mat_peda_sequence'):
        op.drop_table(table)
    op.drop_table('mat_peda')


def downgrade():
    raise NotImplementedError('La fusion en mat_peda (colonnes supprimées de media) n\'est pas restaurée.')
