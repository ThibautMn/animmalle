"""Contrats JSON : identifiants étrangers explicites, champs inconnus refusés."""
import re

import nh3
from marshmallow import Schema, fields, validate

RICH_TAGS = {'span', 'i', 'hr', 'table', 'thead', 'tbody', 'tr', 'th', 'td', 'colgroup', 'col', 'p', 'br', 'strong', 'em', 'u', 's', 'ul', 'ol', 'li', 'a', 'h1', 'h2', 'h3', 'blockquote'}


ICON_CLASS = re.compile(r'^pi pi-[a-z0-9-]+$')


def rich_attribute(tag, attribute, value):
    # une icône n'a que sa classe PrimeIcons ; les autres éléments, ni classe ni script
    if tag == 'i':
        return value if attribute == 'class' and ICON_CLASS.match(value) else None
    return value


class RichText(fields.String):
    """Texte issu de l'éditeur WYSIWYG : HTML nettoyé ; le texte brut reste inchangé."""

    def _deserialize(self, value, attr, data, **kwargs):
        value = super()._deserialize(value, attr, data, **kwargs)
        return nh3.clean(value, tags=RICH_TAGS, attributes={'a': {'href'}, 'i': {'class'}, 'table': {'style'}, 'col': {'style'},
                                     'th': {'colspan', 'rowspan', 'data-colwidth'},
                                     'td': {'colspan', 'rowspan', 'data-colwidth'}, 'span': {'style'}, 'p': {'style'},
                                     'h1': {'style'}, 'h2': {'style'}, 'h3': {'style'}},
                         filter_style_properties={'color', 'text-align', 'font-size', 'width', 'min-width'}, attribute_filter=rich_attribute,
                         url_schemes={'http', 'https', 'mailto'}, link_rel='noopener noreferrer')


def text_field(limit=100000, **kwargs):
    return fields.String(validate=validate.Length(max=limit), **kwargs)


def rich_field(limit=100000, **kwargs):
    return RichText(validate=validate.Length(max=limit), **kwargs)


def identifier(**kwargs):
    return fields.Integer(strict=True, validate=validate.Range(min=1), **kwargs)


class LoginSchema(Schema):
    login = fields.String(required=True, validate=validate.Length(min=1, max=200))
    password = fields.String(required=True, validate=validate.Length(min=1, max=1000), load_only=True)


class SequenceSchema(Schema):
    id = identifier()
    titre = text_field(100, required=True)
    objectifs = rich_field(load_default='')
    description = rich_field(load_default='')
    materiel_div = rich_field(load_default='')
    fk_modalite_id = identifier(required=True)
    fk_approche_id = identifier(required=True)
    duree_minutes = fields.Integer(strict=True, required=True, validate=validate.Range(min=1, max=1440))
    fk_type_seq_id = identifier(required=True)
    materiel = fields.List(identifier(), load_default=list, validate=validate.Length(max=1000))


class AnimationSchema(Schema):
    id = fields.String(dump_only=True)
    titre = fields.String(required=True, validate=validate.Length(min=1, max=100))
    statut = fields.Integer(strict=True, required=True, validate=validate.OneOf([1, 2, 3]))
    description = rich_field(load_default='')
    auteurs = text_field(dump_only=True)
    pre_anim = rich_field(load_default='')
    post_anim = rich_field(load_default='')
    objectifs = rich_field(load_default='')
    lieu = text_field(allow_none=True, load_default='')
    fk_duree_id = identifier(allow_none=True, load_default=None)
    public_specifique = rich_field(load_default='')
    date_modif = fields.Date(dump_only=True)
    sequences = fields.List(fields.Nested(SequenceSchema), load_default=list, validate=validate.Length(max=500))
    tags = fields.List(identifier(), load_default=list, validate=validate.Length(max=1000))


class MaterialSchema(Schema):
    id = identifier(dump_only=True)
    nom = fields.String(required=True, validate=validate.Length(min=1, max=100))
    fk_type_mat_id = identifier(required=True)
    description = rich_field(load_default='')
    localisation = text_field(50, load_default='')
    variante = rich_field(load_default='')
    difficulte_id = identifier(allow_none=True, load_default=None)
    materiel = rich_field(load_default='')
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
