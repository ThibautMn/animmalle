"""Écritures métier atomiques, sans commit implicite."""
from pathlib import Path
from datetime import date
from uuid import uuid4

from flask import g, abort
from marshmallow import ValidationError
from sqlalchemy import select, delete, or_

from .models import (Animation, Sequence, MatPeda, Thesaurus, Commentaire,
                     RelAnimSequence, RelAnimTag, RelMatPedaSequence, RelMatPedaThematique)


def get(model, key):
    item = g.db.get(model, key)
    if item is None:
        abort(404, description='Élément introuvable.')
    return item


def visible_animations():
    if g.is_admin:
        return True
    return or_(Animation.statut == 1, Animation.auteurs == g.user['name'])


def read_animation(key):
    item = get(Animation, key)
    if not g.is_admin and item.statut != 1 and item.auteurs != g.user['name']:
        abort(403, description='Animation privée.')
    return item


def edit_animation(item):
    if not g.is_admin and (item.auteurs != g.user['name'] or item.statut == 1):
        abort(403, description='Modification interdite.')


def reference(key, family=None):
    if key is None:
        return
    item = g.db.get(Thesaurus, key)
    if item is None or (family and item.reference not in family):
        raise ValidationError({'references': [f'Référence {key} absente ou de catégorie incorrecte.']})


def replace_links(model, owner_column, owner_id, target_column, ids):
    g.db.execute(delete(model).where(getattr(model, owner_column) == owner_id))
    for key in dict.fromkeys(ids):
        g.db.add(model(**{owner_column: owner_id, target_column: key}))


def orphan_sequence(key):
    if not g.db.scalar(select(RelAnimSequence.id).where(RelAnimSequence.fk_sequence_id == key)):
        g.db.execute(delete(RelMatPedaSequence).where(RelMatPedaSequence.fk_sequence_id == key))
        g.db.execute(delete(Sequence).where(Sequence.id == key))


def save_animation(data, item=None):
    creating = item is None
    if item is not None:
        edit_animation(item)
    if data['statut'] == 1 and not g.is_admin:
        abort(403, description='Seul un administrateur peut valider une animation.')
    reference(data['fk_duree_id'], ['ref.duree'])
    for key in data['tags']:
        reference(key)
    sequences = data.pop('sequences')
    tags = data.pop('tags')
    # Valider toutes les appartenances avant la première écriture.
    old_ids = set() if creating else set(g.db.scalars(select(RelAnimSequence.fk_sequence_id).where(RelAnimSequence.fk_anim_id == item.id)))
    submitted_ids = [seq['id'] for seq in sequences if 'id' in seq]
    if len(submitted_ids) != len(set(submitted_ids)) or not set(submitted_ids) <= old_ids:
        raise ValidationError({'sequences': ['Séquence dupliquée ou appartenant à une autre animation.']})
    for seq in sequences:
        for key, family in (('fk_duree_id', 'ref.duree_seq'), ('fk_modalite_id', 'ref.modalites'),
                            ('fk_approche_id', 'ref.approches'), ('fk_type_seq_id', 'ref.type_seq')):
            reference(seq[key], [family])
        for key in seq['materiel']:
            if not g.db.get(MatPeda, key):
                raise ValidationError({'materiel': [f'Matériel {key} introuvable.']})
        if 'id' in seq:
            owners = list(g.db.scalars(select(RelAnimSequence.fk_anim_id).where(RelAnimSequence.fk_sequence_id == seq['id'])))
            if any(owner != item.id for owner in owners):
                raise ValidationError({'sequences': ['Une séquence partagée ne peut être modifiée directement.']})
    if creating:
        item = Animation(id=uuid4().hex, auteurs=g.user['name'])
        g.db.add(item)
    for key, value in data.items():
        setattr(item, key, value)
    item.date_modif = date.today()
    g.db.flush()
    replace_links(RelAnimTag, 'fk_anim_id', item.id, 'fk_thes_id', tags + ([item.fk_duree_id] if item.fk_duree_id else []))
    # L'ordre est porté par les identifiants des relations, comme dans l'historique.
    g.db.execute(delete(RelAnimSequence).where(RelAnimSequence.fk_anim_id == item.id))
    for seq in sequences:
        materials = seq.pop('materiel')
        key = seq.pop('id', None)
        obj = get(Sequence, key) if key else Sequence()
        for name, value in seq.items():
            setattr(obj, name, value)
        g.db.add(obj)
        g.db.flush()
        g.db.add(RelAnimSequence(fk_anim_id=item.id, fk_sequence_id=obj.id))
        replace_links(RelMatPedaSequence, 'fk_sequence_id', obj.id, 'fk_mat_peda_id', materials)
    g.db.flush()
    for key in old_ids - set(submitted_ids):
        orphan_sequence(key)
    g.db.expire(item, ['sequences', 'tags'])
    return item


def delete_animation(item):
    edit_animation(item)
    ids = list(g.db.scalars(select(RelAnimSequence.fk_sequence_id).where(RelAnimSequence.fk_anim_id == item.id)))
    for model in (RelAnimTag, RelAnimSequence):
        g.db.execute(delete(model).where(model.fk_anim_id == item.id))
    for key in ids:
        orphan_sequence(key)
    g.db.execute(delete(Commentaire).where(Commentaire.fk_id_anim_id == item.id))
    g.db.delete(item)


def save_material(data, item=None):
    reference(data['fk_type_mat_id'], ['ref.type_mat', 'ref.type_outil'])
    reference(data['difficulte_id'], ['ref.difficulte'])
    reference(data['fk_type_mat_outil_id'], ['ref.type_mat'])
    for key in data['thematiques']:
        reference(key, ['ref.thematiques'])
    themes = data.pop('thematiques')
    if item is None:
        item = MatPeda(url='')
        g.db.add(item)
    for key, value in data.items():
        setattr(item, key, value)
    item.date_modif = date.today()
    g.db.flush()
    replace_links(RelMatPedaThematique, 'fk_mat_peda_id', item.id, 'fk_thes_id', themes)
    g.db.flush()
    g.db.expire(item, ['thematiques'])
    return item


def animation_dict(item):
    from .schemas import AnimationSchema, SequenceSchema
    result = AnimationSchema(exclude=['sequences', 'tags']).dump(item)
    result['tags'] = [tag.id for tag in item.tags]
    result['sequences'] = []
    for seq in item.sequences:
        value = SequenceSchema(exclude=['materiel']).dump(seq)
        value['materiel'] = [mat.id for mat in seq.materiel]
        result['sequences'].append(value)
    return result


def material_dict(item):
    from .schemas import MaterialSchema
    result = MaterialSchema(exclude=['thematiques', 'url']).dump(item)
    result['has_file'] = bool(item.url)
    # Extension seule (jamais le chemin) : le frontend choisit l'icône ou la vignette.
    result['extension'] = Path(item.url).suffix.lower().lstrip('.') if item.url else ''
    result['thematiques'] = [tag.id for tag in item.thematiques]
    return result
