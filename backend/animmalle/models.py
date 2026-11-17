"""Schéma métier historique adapté à PostgreSQL, sans connexion implicite."""

from sqlalchemy import Date, DateTime, ForeignKey, Integer, MetaData, String, Text, UniqueConstraint, text
from sqlalchemy.orm import DeclarativeBase, mapped_column, relationship


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention={
        'pk': 'pk_%(table_name)s',
        'fk': 'fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s',
        'uq': 'uq_%(table_name)s_%(column_0_name)s',
        'ix': 'ix_%(table_name)s_%(column_0_name)s',
    })


class Thesaurus(Base):
    __tablename__ = 'thesaurus'
    __table_args__ = (UniqueConstraint('label'),)

    id = mapped_column(Integer, primary_key=True)
    reference = mapped_column(Text, nullable=True, default='', server_default=text("''"))
    label = mapped_column(String(80), nullable=True)
    code = mapped_column(Text, nullable=True, default='', server_default=text("''"))
    # Ordre d'affichage parmi les termes de même référence (formulaires, listes de cases à cocher).
    position = mapped_column(Integer, nullable=False, default=0, server_default=text('0'))


class Animation(Base):
    __tablename__ = 'animation'

    id = mapped_column(String(40), primary_key=True)
    titre = mapped_column(String(100), nullable=False)
    statut = mapped_column(Integer, nullable=False)
    description = mapped_column(Text, nullable=False)
    auteurs = mapped_column(Text, nullable=False)
    pre_anim = mapped_column(Text, nullable=False)
    post_anim = mapped_column(Text, nullable=False)
    objectifs = mapped_column(Text, nullable=False)
    lieu = mapped_column(Text, nullable=True)
    fk_duree_id = mapped_column(Integer, ForeignKey('thesaurus.id'), index=True, nullable=True)
    public_specifique = mapped_column(Text, nullable=False)
    date_modif = mapped_column(Date, nullable=True, server_default=text('CURRENT_DATE'))
    fk_duree = relationship('Thesaurus', foreign_keys=[fk_duree_id])
    sequences = relationship('Sequence', secondary='rel_anim_sequence', viewonly=True, order_by='RelAnimSequence.id')
    tags = relationship('Thesaurus', secondary='rel_anim_tag', viewonly=True)
    commentaires = relationship('Commentaire', back_populates='fk_id_anim', passive_deletes='all')


class Sequence(Base):
    __tablename__ = 'sequence'

    id = mapped_column(Integer, primary_key=True)
    titre = mapped_column(String(100), nullable=False)
    objectifs = mapped_column(Text, nullable=False)
    fk_modalite_id = mapped_column(Integer, ForeignKey('thesaurus.id'), index=True, nullable=False)
    fk_approche_id = mapped_column(Integer, ForeignKey('thesaurus.id'), index=True, nullable=False)
    description = mapped_column(Text, nullable=False)
    materiel_div = mapped_column(Text, nullable=False)
    duree_minutes = mapped_column(Integer, nullable=False)
    fk_type_seq_id = mapped_column(Integer, ForeignKey('thesaurus.id'), index=True, nullable=False)
    fk_modalite = relationship('Thesaurus', foreign_keys=[fk_modalite_id])
    fk_approche = relationship('Thesaurus', foreign_keys=[fk_approche_id])
    fk_type_seq = relationship('Thesaurus', foreign_keys=[fk_type_seq_id])
    materiel = relationship('Media', secondary='rel_media_sequence', viewonly=True)


class Media(Base):
    """Média de la médiathèque (image, vidéo, document…), issu des lignes `ref.type_mat` de `mat_peda`."""
    __tablename__ = 'media'

    id = mapped_column(Integer, primary_key=True)
    fk_type_mat_id = mapped_column(Integer, ForeignKey('thesaurus.id'), index=True, nullable=False)
    nom = mapped_column(String(100), nullable=False)
    description = mapped_column(Text, nullable=False)
    url = mapped_column(String(250), nullable=False)
    date_modif = mapped_column(Date, nullable=True, server_default=text('CURRENT_DATE'))
    fk_type_mat = relationship('Thesaurus', foreign_keys=[fk_type_mat_id])
    sequence = relationship('Sequence', secondary='rel_media_sequence', viewonly=True)
    thematiques = relationship('Thesaurus', secondary='rel_media_thematique', viewonly=True)


class OutilFacilitateur(Base):
    """Outil facilitateur, issu des lignes `ref.type_outil` de `mat_peda`."""
    __tablename__ = 'outil_facilitateur'

    id = mapped_column(Integer, primary_key=True)
    fk_type_outil_id = mapped_column(Integer, ForeignKey('thesaurus.id'), index=True, nullable=False)
    nom = mapped_column(String(100), nullable=False)
    description = mapped_column(Text, nullable=False)
    url = mapped_column(String(250), nullable=False)
    variante = mapped_column(Text, nullable=False)
    difficulte_id = mapped_column(Integer, ForeignKey('thesaurus.id'), index=True, nullable=True)
    materiel = mapped_column(Text, nullable=False)
    date_modif = mapped_column(Date, nullable=True, server_default=text('CURRENT_DATE'))
    # Type du média (ref.type_mat) associé à l'outil quand il a un fichier.
    fk_type_mat_outil_id = mapped_column(Integer, ForeignKey('thesaurus.id'), index=True, nullable=True)
    fk_type_outil = relationship('Thesaurus', foreign_keys=[fk_type_outil_id])
    difficulte = relationship('Thesaurus', foreign_keys=[difficulte_id])
    fk_type_mat_outil = relationship('Thesaurus', foreign_keys=[fk_type_mat_outil_id])


class Commentaire(Base):
    __tablename__ = 'commentaire'

    id = mapped_column(Integer, primary_key=True)
    fk_id_anim_id = mapped_column(String(40), ForeignKey('animation.id'), index=True, nullable=False)
    date = mapped_column(Date, nullable=False)
    auteur = mapped_column(String(100), nullable=False)
    commentaire = mapped_column(Text, nullable=False)
    fk_id_anim = relationship('Animation', foreign_keys=[fk_id_anim_id], back_populates='commentaires')


class RelAnimSequence(Base):
    __tablename__ = 'rel_anim_sequence'
    __table_args__ = (UniqueConstraint('fk_anim_id', 'fk_sequence_id', name='uq_rel_anim_sequence_pair'),)

    id = mapped_column(Integer, primary_key=True)
    fk_anim_id = mapped_column(String(40), ForeignKey('animation.id'), index=True, nullable=False)
    fk_sequence_id = mapped_column(Integer, ForeignKey('sequence.id'), index=True, nullable=False)
    fk_anim = relationship('Animation', foreign_keys=[fk_anim_id])
    fk_sequence = relationship('Sequence', foreign_keys=[fk_sequence_id])


class RelAnimTag(Base):
    __tablename__ = 'rel_anim_tag'
    __table_args__ = (UniqueConstraint('fk_anim_id', 'fk_thes_id', name='uq_rel_anim_tag_pair'),)

    id = mapped_column(Integer, primary_key=True)
    fk_anim_id = mapped_column(String(40), ForeignKey('animation.id'), index=True, nullable=False)
    fk_thes_id = mapped_column(Integer, ForeignKey('thesaurus.id'), index=True, nullable=False)
    fk_anim = relationship('Animation', foreign_keys=[fk_anim_id])
    fk_thes = relationship('Thesaurus', foreign_keys=[fk_thes_id])


class RelMediaSequence(Base):
    __tablename__ = 'rel_media_sequence'
    __table_args__ = (UniqueConstraint('fk_media_id', 'fk_sequence_id', name='uq_rel_media_sequence_pair'),)

    id = mapped_column(Integer, primary_key=True)
    fk_media_id = mapped_column(Integer, ForeignKey('media.id'), index=True, nullable=False)
    fk_sequence_id = mapped_column(Integer, ForeignKey('sequence.id'), index=True, nullable=False)
    fk_media = relationship('Media', foreign_keys=[fk_media_id])
    fk_sequence = relationship('Sequence', foreign_keys=[fk_sequence_id])


class RelMediaThematique(Base):
    __tablename__ = 'rel_media_thematique'
    __table_args__ = (UniqueConstraint('fk_media_id', 'fk_thes_id', name='uq_rel_media_thematique_pair'),)

    id = mapped_column(Integer, primary_key=True)
    fk_media_id = mapped_column(Integer, ForeignKey('media.id'), index=True, nullable=False)
    fk_thes_id = mapped_column(Integer, ForeignKey('thesaurus.id'), index=True, nullable=False)
    fk_media = relationship('Media', foreign_keys=[fk_media_id])
    fk_thes = relationship('Thesaurus', foreign_keys=[fk_thes_id])


# Tables propres à la nouvelle application : absentes du dump historique, donc ignorées par la restauration.
APPLICATION_TABLES = frozenset({'taxon_media', 'evenement_usage'})


class TaxonMedia(Base):
    """Taxon TaxHub dont au moins un média existe : mémorisé pour ne plus interroger TaxHub."""
    __tablename__ = 'taxon_media'
    __table_args__ = (UniqueConstraint('cd_ref'),)

    id = mapped_column(Integer, primary_key=True)
    cd_ref = mapped_column(Integer, nullable=False)
    lb_nom = mapped_column(String(250), nullable=False)
    nom_vern = mapped_column(Text, nullable=True)
    nom_valide = mapped_column(Text, nullable=True)
    group2_inpn = mapped_column(String(100), nullable=True)


class EvenementUsage(Base):
    """Connexion, consultation ou téléchargement, pour les statistiques (aucune donnée personnelle)."""
    __tablename__ = 'evenement_usage'

    id = mapped_column(Integer, primary_key=True)
    date = mapped_column(DateTime, nullable=False, index=True, server_default=text('CURRENT_TIMESTAMP'))
    type = mapped_column(String(20), nullable=False)  # connexion | consultation | telechargement
    ressource = mapped_column(String(20), nullable=True)  # animation | outil
    ressource_id = mapped_column(String(40), nullable=True)
