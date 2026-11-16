"""Contrats JSON : identifiants étrangers explicites, champs inconnus refusés."""
from marshmallow import Schema, fields, validate


def text_field(limit=100000, **kwargs):
    return fields.String(validate=validate.Length(max=limit), **kwargs)


def identifier(**kwargs):
    return fields.Integer(strict=True, validate=validate.Range(min=1), **kwargs)


class LoginSchema(Schema):
    login = fields.String(required=True, validate=validate.Length(min=1, max=200))
    password = fields.String(required=True, validate=validate.Length(min=1, max=1000), load_only=True)


class SequenceSchema(Schema):
    id = identifier()
    titre = text_field(100, required=True)
    objectifs = text_field(load_default='')
    description = text_field(load_default='')
    materiel_div = text_field(load_default='')
    fk_modalite_id = identifier(required=True)
    fk_approche_id = identifier(required=True)
    duree_minutes = fields.Integer(strict=True, required=True, validate=validate.Range(min=1, max=1440))
    fk_type_seq_id = identifier(required=True)
    materiel = fields.List(identifier(), load_default=list, validate=validate.Length(max=1000))


class AnimationSchema(Schema):
    id = fields.String(dump_only=True)
    titre = fields.String(required=True, validate=validate.Length(min=1, max=100))
    statut = fields.Integer(strict=True, required=True, validate=validate.OneOf([1, 2, 3]))
    description = text_field(load_default='')
    auteurs = text_field(dump_only=True)
    pre_anim = text_field(load_default='')
    post_anim = text_field(load_default='')
    objectifs = text_field(load_default='')
    lieu = text_field(allow_none=True, load_default='')
    fk_duree_id = identifier(allow_none=True, load_default=None)
    public_specifique = text_field(load_default='')
    date_modif = fields.Date(dump_only=True)
    sequences = fields.List(fields.Nested(SequenceSchema), load_default=list, validate=validate.Length(max=500))
    tags = fields.List(identifier(), load_default=list, validate=validate.Length(max=1000))


class MaterialSchema(Schema):
    id = identifier(dump_only=True)
    nom = fields.String(required=True, validate=validate.Length(min=1, max=100))
    fk_type_mat_id = identifier(required=True)
    description = text_field(load_default='')
    localisation = text_field(50, load_default='')
    variante = text_field(load_default='')
    difficulte_id = identifier(allow_none=True, load_default=None)
    materiel = text_field(load_default='')
    fk_type_mat_outil_id = identifier(allow_none=True, load_default=None)
    url = text_field(250, dump_only=True)
    date_modif = fields.Date(dump_only=True)
    thematiques = fields.List(identifier(), load_default=list, validate=validate.Length(max=1000))


class ThesaurusSchema(Schema):
    id = identifier(dump_only=True)
    reference = text_field(200, required=True)
    label = fields.String(required=True, validate=validate.Length(min=1, max=80))
    code = text_field(200, load_default='')


class CommentSchema(Schema):
    id = identifier(dump_only=True)
    auteur = text_field(100, dump_only=True)
    date = fields.Date(dump_only=True)
    commentaire = fields.String(required=True, validate=validate.Length(min=1, max=100000))


class PageSchema(Schema):
    contenu = text_field(1000000, required=True)


class AuthorSchema(Schema):
    auteurs = fields.String(required=True, validate=validate.Length(min=1, max=200))
