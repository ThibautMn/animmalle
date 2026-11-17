"""API JSON version initiale ; toutes les mutations utilisent POST/PUT/DELETE."""
from datetime import date, timedelta
import json

from flask import Blueprint, abort, g, request, session, current_app, send_file
from marshmallow import ValidationError
from sqlalchemy import select, delete, text, or_, func
from sqlalchemy.orm import aliased, load_only
from werkzeug.utils import secure_filename

from .auth import authenticate, can_edit_thesaurus, is_admin, login_user, require_admin, require_thesaurus_editor
from .models import (Animation, Media, OutilFacilitateur, Thesaurus, Commentaire,
                     RelMediaSequence, RelMediaThematique, RelAnimTag, RelAnimSequence, Sequence)
from .schemas import (LoginSchema, AnimationSchema, MediaSchema, OutilSchema, ThesaurusSchema,
                      CommentSchema, PageSchema, AuthorSchema)
from . import services as svc
from . import files
from . import kit
from . import taxhub

api = Blueprint('api', __name__)
MIN_SEARCH_CHARS = 3


def payload(schema):
    return schema.load(request.get_json())


def integer_arg(name, default, minimum=1, maximum=1000000):
    value = request.args.get(name, str(default))
    try:
        number = int(value)
    except (TypeError, ValueError):
        raise ValidationError({name: ['Entier requis.']}) from None
    if not minimum <= number <= maximum:
        raise ValidationError({name: ['Valeur hors limites.']})
    return number


def id_args(name):
    result = []
    for value in request.args.getlist(name):
        try:
            key = int(value)
            if key < 1:
                raise ValueError
        except ValueError:
            raise ValidationError({name: ['Identifiant entier positif requis.']}) from None
        result.append(key)
    return set(result)


def paginate(items):
    page = integer_arg('page', 1)
    size = integer_arg('page_size', 50, maximum=200)
    return {'items': items[(page - 1) * size:page * size], 'total': len(items), 'page': page, 'page_size': size}


@api.get('/health')
def health():
    g.db.execute(text('SELECT 1'))
    return {'status': 'ok'}


@api.get('/auth/session')
def auth_session():
    user = session.get('user')
    return {'user': user, 'is_admin': is_admin(user), 'can_edit_thesaurus': can_edit_thesaurus(user),
            'csrf_token': session['csrf_token']}


@api.post('/auth/login')
def login():
    data = payload(LoginSchema())
    user = authenticate(data['login'].strip(), data['password'])
    if not user:
        abort(401, description='Identifiants invalides.')
    login_user(user)
    return auth_session()


@api.post('/auth/logout')
def logout():
    session.clear()
    return '', 204


def animation_query():
    """Requête filtrée de la liste, partagée avec la navigation précédente/suivante."""
    query = select(Animation).options(load_only(Animation.id, Animation.titre, Animation.statut,
                                                 Animation.description, Animation.auteurs,
                                                 Animation.objectifs)).where(svc.visible_animations()).order_by(Animation.titre, Animation.id)
    if 'auteur' in request.args:
        query = query.where(Animation.auteurs == request.args['auteur'])
    statuts = request.args.getlist('statut')
    if statuts:
        try:
            values = {int(value) for value in statuts}
        except ValueError:
            raise ValidationError({'statut': ['Entier requis.']}) from None
        if not values <= {1, 2, 3}:
            raise ValidationError({'statut': ['Valeur hors limites.']})
        query = query.where(Animation.statut.in_(values))
    # Chaque paramètre q répété est un critère supplémentaire (ET) sur le titre, la description ou les objectifs.
    for text_query in (value.strip() for value in request.args.getlist('q')):
        if not text_query:
            continue
        if len(text_query) > 100:
            raise ValidationError({'q': ['100 caractères maximum.']})
        pattern = '%' + text_query.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_') + '%'
        query = query.where(or_(Animation.titre.ilike(pattern, escape='\\'),
                                Animation.description.ilike(pattern, escape='\\'),
                                Animation.objectifs.ilike(pattern, escape='\\')))
    # Durée cumulée des séquences comprise entre duree_min et duree_max (bornes incluses, en minutes).
    if 'duree_min' in request.args or 'duree_max' in request.args:
        total = (select(func.coalesce(func.sum(Sequence.duree_minutes), 0))
                 .join(RelAnimSequence, RelAnimSequence.fk_sequence_id == Sequence.id)
                 .where(RelAnimSequence.fk_anim_id == Animation.id).scalar_subquery())
        if 'duree_min' in request.args:
            query = query.where(total >= integer_arg('duree_min', 0, minimum=0, maximum=100000))
        if 'duree_max' in request.args:
            query = query.where(total <= integer_arg('duree_max', 0, minimum=0, maximum=100000))
    tags = id_args('tag')
    if tags:
        counts = (select(RelAnimTag.fk_anim_id, func.count().label('matched'))
                  .where(RelAnimTag.fk_thes_id.in_(tags)).group_by(RelAnimTag.fk_anim_id).subquery())
        query = (query.join(counts, counts.c.fk_anim_id == Animation.id)
                 .order_by(None).order_by(counts.c.matched.desc(), Animation.titre, Animation.id))
        query = query.add_columns(counts.c.matched)
    return query, tags


@api.get('/animations')
def animations():
    query, tags = animation_query()
    page = integer_arg('page', 1)
    size = integer_arg('page_size', 50, maximum=200)
    total = g.db.scalar(select(func.count()).select_from(query.order_by(None).subquery()))
    query = query.offset((page - 1) * size).limit(size)
    rows = g.db.execute(query).all()
    ids = [row[0].id for row in rows]
    tags_by_anim = {key: [] for key in ids}
    if ids:
        for anim_id, tag_id in g.db.execute(select(RelAnimTag.fk_anim_id, RelAnimTag.fk_thes_id)
                                            .where(RelAnimTag.fk_anim_id.in_(ids)).order_by(RelAnimTag.id)):
            tags_by_anim[anim_id].append(tag_id)
    # Durée totale = somme des durées de séquences de chaque animation de la page.
    totals = {}
    if ids:
        totals = dict(g.db.execute(select(RelAnimSequence.fk_anim_id, func.sum(Sequence.duree_minutes))
                                   .join(Sequence, Sequence.id == RelAnimSequence.fk_sequence_id)
                                   .where(RelAnimSequence.fk_anim_id.in_(ids))
                                   .group_by(RelAnimSequence.fk_anim_id)).all())
    # Bornes des durées cumulées parmi toutes les animations visibles, indépendamment des filtres.
    # Une animation sans séquence compte pour 0 minute.
    per_animation = (select(func.coalesce(func.sum(Sequence.duree_minutes), 0).label('total'))
                     .select_from(Animation)
                     .outerjoin(RelAnimSequence, RelAnimSequence.fk_anim_id == Animation.id)
                     .outerjoin(Sequence, Sequence.id == RelAnimSequence.fk_sequence_id)
                     .where(svc.visible_animations()).group_by(Animation.id).subquery())
    shortest, longest = (int(value or 0) for value in g.db.execute(
        select(func.min(per_animation.c.total), func.max(per_animation.c.total))).one())
    items = [{'id': row[0].id, 'titre': row[0].titre, 'statut': row[0].statut,
              'description': row[0].description, 'objectifs': row[0].objectifs, 'auteurs': row[0].auteurs,
              'tags': tags_by_anim[row[0].id], 'duree_minutes': int(totals.get(row[0].id, 0)),
              'fk_duree_id': row[0].fk_duree_id,
              'pertinence': {'matched': row[1] if tags else 0, 'requested': len(tags)}}
             for row in rows]
    return {'items': items, 'total': total, 'page': page, 'page_size': size, 'duree_min': shortest, 'duree_max': longest}


@api.get('/animations/<key>/neighbors')
def animation_neighbors(key):
    """Animations voisines de `key` dans la liste filtrée (mêmes paramètres que /animations)."""
    query, _ = animation_query()
    rows = [(row[0].id, row[0].titre) for row in g.db.execute(query)]
    position = next((index for index, row in enumerate(rows) if row[0] == key), None)
    if position is None:
        return {'found': False, 'previous': None, 'next': None, 'position': None, 'total': len(rows)}

    def brief(row):
        return {'id': row[0], 'titre': row[1]} if row else None
    return {'found': True, 'position': position + 1, 'total': len(rows),
            'previous': brief(rows[position - 1] if position > 0 else None),
            'next': brief(rows[position + 1] if position + 1 < len(rows) else None)}


@api.get('/animations/<key>')
def animation(key):
    return svc.animation_dict(svc.read_animation(key))


@api.post('/animations')
def create_animation():
    item = svc.save_animation(payload(AnimationSchema()))
    result = svc.animation_dict(item)
    g.db.commit()
    return result, 201


@api.put('/animations/<key>')
def update_animation(key):
    item = svc.save_animation(payload(AnimationSchema()), svc.get(Animation, key))
    result = svc.animation_dict(item)
    g.db.commit()
    return result


@api.delete('/animations/<key>')
def remove_animation(key):
    svc.delete_animation(svc.get(Animation, key))
    g.db.commit()
    return '', 204


@api.post('/animations/<key>/validate')
def validate_animation(key):
    require_admin()
    item = svc.get(Animation, key)
    item.statut = 1
    item.date_modif = date.today()
    g.db.commit()
    return svc.animation_dict(item)


@api.put('/animations/<key>/author')
def change_author(key):
    require_admin()
    data = payload(AuthorSchema())
    item = svc.get(Animation, key)
    item.auteurs = data['auteurs']
    item.date_modif = date.today()
    g.db.commit()
    return svc.animation_dict(item)


@api.get('/animations/<key>/comments')
def comments(key):
    svc.read_animation(key)
    return {'items': CommentSchema(many=True).dump(g.db.scalars(select(Commentaire).where(Commentaire.fk_id_anim_id == key).order_by(Commentaire.date, Commentaire.id)))}


@api.post('/animations/<key>/comments')
def add_comment(key):
    svc.read_animation(key)
    item = Commentaire(fk_id_anim_id=key, auteur=g.user['name'], date=date.today(), **payload(CommentSchema()))
    g.db.add(item)
    g.db.commit()
    return CommentSchema().dump(item), 201


@api.delete('/animations/<key>/comments/<int:comment_id>')
def remove_comment(key, comment_id):
    svc.read_animation(key)
    item = svc.get(Commentaire, comment_id)
    if item.fk_id_anim_id != key:
        abort(404)
    if not g.is_admin and item.auteur != g.user['name']:
        abort(403)
    g.db.delete(item)
    g.db.commit()
    return '', 204


def search_terms():
    """Chaque paramètre q répété est un critère (ET) : renvoie (motif LIKE, motif d'extension) échappés."""
    for text_query in (value.strip() for value in request.args.getlist('q')):
        if not text_query:
            continue
        if len(text_query) > 100:
            raise ValidationError({'q': ['100 caractères maximum.']})
        escaped = text_query.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')
        yield f'%{escaped}%', f'%.{escaped}'


def like(column, pattern):
    return column.ilike(pattern, escape='\\')


def multipart_data(schema):
    """Corps JSON, ou multipart avec le champ `data` (JSON) et un fichier optionnel `file`."""
    if request.mimetype == 'multipart/form-data':
        try:
            data = json.loads(request.form.get('data', ''))
        except ValueError:
            raise ValidationError({'data': ['Objet JSON requis.']}) from None
        return schema.load(data)
    return payload(schema)


def upload_file(item):
    file = request.files.get('file')
    if not file:
        abort(422, description='Champ multipart file requis.')
    item.url = files.store_upload(file)
    item.date_modif = date.today()
    g.db.commit()
    return item


@api.get('/media')
def media_list():
    type_alias = aliased(Thesaurus)
    query = select(Media).outerjoin(type_alias, type_alias.id == Media.fk_type_mat_id).order_by(Media.nom, Media.id)
    types = id_args('type')
    if types:
        query = query.where(Media.fk_type_mat_id.in_(types))
    for pattern, extension in search_terms():
        theme_alias = aliased(Thesaurus)
        theme = (select(RelMediaThematique.id)
                 .join(theme_alias, theme_alias.id == RelMediaThematique.fk_thes_id)
                 .where(RelMediaThematique.fk_media_id == Media.id, like(theme_alias.label, pattern)))
        query = query.where(or_(like(Media.nom, pattern), like(Media.description, pattern),
                                like(Media.url, extension), like(type_alias.label, pattern), theme.exists()))
    tags = id_args('tag')
    result = []
    for item in g.db.scalars(query):
        matched = len(tags & {tag.id for tag in item.thematiques})
        if tags and not matched:
            continue
        value = svc.media_dict(item)
        value['pertinence'] = {'matched': matched, 'requested': len(tags)}
        result.append(value)
    if tags:
        result.sort(key=lambda item: -item['pertinence']['matched'])
    return paginate(result)


@api.get('/media/<int:key>')
def media(key):
    return svc.media_dict(svc.get(Media, key))


@api.post('/media')
def create_media():
    item = svc.save_media(multipart_data(MediaSchema()))
    if file := request.files.get('file'):
        item.url = files.store_upload(file)
    result = svc.media_dict(item)
    g.db.commit()
    return result, 201


@api.put('/media/<int:key>')
def update_media(key):
    require_admin()
    item = svc.save_media(payload(MediaSchema()), svc.get(Media, key))
    result = svc.media_dict(item)
    g.db.commit()
    return result


@api.delete('/media/<int:key>')
def remove_media(key):
    require_admin()
    item = svc.get(Media, key)
    for model in (RelMediaSequence, RelMediaThematique):
        g.db.execute(delete(model).where(model.fk_media_id == key))
    g.db.delete(item)
    g.db.commit()
    # Garder les fichiers : d'autres notices peuvent les référencer.
    return '', 204


@api.post('/media/<int:key>/file')
def upload_media(key):
    require_admin()
    return svc.media_dict(upload_file(svc.get(Media, key)))


@api.get('/media/<int:key>/preview')
def preview_media(key):
    source, mime = files.preview_file(svc.get(Media, key), native=request.args.get('natif') == '1')
    response = send_file(source, mimetype=mime, download_name='apercu.pdf' if mime == 'application/pdf' else None)
    response.headers['Cache-Control'] = 'no-store'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    return response


@api.get('/media/<int:key>/thumbnail')
def thumbnail_media(key):
    response = send_file(files.thumbnail_file(svc.get(Media, key)), mimetype='image/jpeg')
    response.headers['Cache-Control'] = 'private, max-age=86400'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    return response


@api.get('/media/<int:key>/file')
def download_media(key):
    source = files.media_path(svc.get(Media, key))
    return send_file(source, as_attachment=True, download_name=source.name)


@api.get('/media/<int:key>/download')
def export_media(key):
    item = svc.get(Media, key)
    return send_file(kit.export_kit(kit.media_fiche(item)), mimetype='application/zip', as_attachment=True,
                     download_name=kit.safe_name(item.nom, 'media') + '.zip')


@api.get('/outils')
def outils_list():
    type_alias, difficulty_alias, media_alias = (aliased(Thesaurus) for _ in range(3))
    query = (select(OutilFacilitateur)
             .outerjoin(type_alias, type_alias.id == OutilFacilitateur.fk_type_outil_id)
             .outerjoin(difficulty_alias, difficulty_alias.id == OutilFacilitateur.difficulte_id)
             .outerjoin(media_alias, media_alias.id == OutilFacilitateur.fk_type_mat_outil_id)
             .order_by(OutilFacilitateur.nom, OutilFacilitateur.id))
    types = id_args('type')
    if types:
        query = query.where(OutilFacilitateur.fk_type_outil_id.in_(types))
    for pattern, extension in search_terms():
        query = query.where(or_(
            like(OutilFacilitateur.nom, pattern), like(OutilFacilitateur.description, pattern),
            like(OutilFacilitateur.variante, pattern), like(OutilFacilitateur.materiel, pattern),
            like(OutilFacilitateur.url, extension), like(type_alias.label, pattern),
            like(difficulty_alias.label, pattern), like(media_alias.label, pattern)))
    return paginate([svc.outil_dict(item) for item in g.db.scalars(query)])


@api.get('/outils/<int:key>')
def outil(key):
    return svc.outil_dict(svc.get(OutilFacilitateur, key))


@api.post('/outils')
def create_outil():
    item = svc.save_outil(multipart_data(OutilSchema()))
    if file := request.files.get('file'):
        item.url = files.store_upload(file)
    result = svc.outil_dict(item)
    g.db.commit()
    return result, 201


@api.put('/outils/<int:key>')
def update_outil(key):
    require_admin()
    item = svc.save_outil(payload(OutilSchema()), svc.get(OutilFacilitateur, key))
    result = svc.outil_dict(item)
    g.db.commit()
    return result


@api.delete('/outils/<int:key>')
def remove_outil(key):
    require_admin()
    g.db.delete(svc.get(OutilFacilitateur, key))
    g.db.commit()
    # Garder les fichiers : d'autres notices peuvent les référencer.
    return '', 204


@api.post('/outils/<int:key>/file')
def upload_outil(key):
    require_admin()
    return svc.outil_dict(upload_file(svc.get(OutilFacilitateur, key)))


@api.get('/outils/<int:key>/file')
def download_outil(key):
    source = files.media_path(svc.get(OutilFacilitateur, key))
    return send_file(source, as_attachment=True, download_name=source.name)


@api.get('/outils/<int:key>/download')
def export_outil(key):
    item = svc.get(OutilFacilitateur, key)
    return send_file(kit.export_kit(kit.outil_fiche(item)), mimetype='application/zip', as_attachment=True,
                     download_name=kit.safe_name(item.nom, 'outil') + '.zip')


@api.get('/taxhub/taxa')
def taxhub_search():
    term = request.args.get('q', '').strip()[:100]
    return {'items': taxhub.search_taxa(term) if len(term) >= MIN_SEARCH_CHARS else []}


@api.get('/taxhub/taxa/<int:cd_ref>')
def taxhub_taxon(cd_ref):
    return taxhub.taxon(cd_ref)


@api.get('/taxhub/taxa/<int:cd_ref>/media')
def taxhub_media(cd_ref):
    return {'items': taxhub.media_list(cd_ref)}


@api.post('/taxhub/import')
def taxhub_import():
    """Copie un média TaxHub dans la médiathèque et renvoie la fiche créée."""
    data = request.get_json(silent=True)
    if not isinstance(data, dict) or type(data.get('cd_ref')) is not int or type(data.get('id_media')) is not int:
        raise ValidationError({'id_media': ['cd_ref et id_media requis.']})
    media, file = taxhub.download_media(data['cd_ref'], data['id_media'], current_app.config['MAX_CONTENT_LENGTH'])
    nom = (media['titre'] or file.filename.rsplit('.', 1)[0])[:100]
    credit = ' - '.join(part for part in (media['auteur'], media['source'], media['licence']) if part)
    fields = MediaSchema().load({'nom': nom, 'fk_type_mat_id': data.get('fk_type_mat_id'),
                                    'description': f'Crédit : {credit}' if credit else '',
                                    'thematiques': data.get('thematiques', [])})
    item = svc.save_media(fields)
    item.url = files.store_upload(file)
    result = svc.media_dict(item)
    g.db.commit()
    return result, 201


@api.get('/thesaurus')
def thesaurus():
    query = select(Thesaurus).order_by(Thesaurus.position, Thesaurus.label, Thesaurus.id)
    if 'reference' in request.args:
        query = query.where(Thesaurus.reference == request.args['reference'])
    return {'items': ThesaurusSchema(many=True).dump(g.db.scalars(query))}


@api.post('/thesaurus')
def create_tag():
    require_thesaurus_editor()
    data = payload(ThesaurusSchema())
    if data['reference']:
        if not g.db.scalar(select(Thesaurus.id).where(Thesaurus.reference == '', Thesaurus.code == data['reference'])):
            raise ValidationError({'reference': ['Catégorie introuvable.']})
    elif not data['code']:
        raise ValidationError({'code': ['Code requis pour une catégorie.']})
    last = g.db.scalar(select(func.max(Thesaurus.position)).where(Thesaurus.reference == data['reference']))
    item = Thesaurus(**data, position=0 if last is None else last + 1)
    g.db.add(item)
    g.db.commit()
    return ThesaurusSchema().dump(item), 201


def label_shared(item):
    # Le pictogramme est nommé d'après le libellé : un autre terme homonyme l'utilise peut-être.
    return bool(g.db.scalar(select(Thesaurus.id).where(Thesaurus.label == item.label, Thesaurus.id != item.id)))


@api.put('/thesaurus/<int:key>')
def update_tag(key):
    require_thesaurus_editor()
    item = svc.get(Thesaurus, key)
    data = payload(ThesaurusSchema(only=('label',)))
    files.rename_pictogram(item, data['label'], shared=label_shared(item))
    item.label = data['label']
    g.db.commit()
    return ThesaurusSchema().dump(item)


@api.put('/thesaurus/<int:key>/move')
def move_tag(key):
    require_thesaurus_editor()
    item = svc.get(Thesaurus, key)
    direction = (request.get_json(silent=True) or {}).get('direction')
    if direction not in ('up', 'down'):
        raise ValidationError({'direction': ['Valeur attendue : up ou down.']})
    siblings = list(g.db.scalars(select(Thesaurus).where(Thesaurus.reference == item.reference).order_by(Thesaurus.position, Thesaurus.label, Thesaurus.id)))
    index = siblings.index(item)
    target = index - 1 if direction == 'up' else index + 1
    if 0 <= target < len(siblings):
        siblings[index], siblings[target] = siblings[target], siblings[index]
    for number, sibling in enumerate(siblings):
        sibling.position = number
    g.db.commit()
    return {'items': ThesaurusSchema(many=True).dump(siblings)}


@api.delete('/thesaurus/<int:key>')
def remove_tag(key):
    require_thesaurus_editor()
    item = svc.get(Thesaurus, key)
    if item.reference == '' and g.db.scalar(select(Thesaurus.id).where(Thesaurus.reference == item.code)):
        abort(409, description='Catégorie encore utilisée.')
    if not label_shared(item):
        try:
            files.pictogram_path(item).unlink(missing_ok=True)
        except Exception:
            pass
    g.db.delete(item)
    g.db.commit()
    return '', 204


@api.get('/pages/<name>')
def page(name):
    result = files.read_page(name)
    result['documents'] = [svc.outil_dict(item) for item in g.db.scalars(select(OutilFacilitateur).join(Thesaurus, Thesaurus.id == OutilFacilitateur.fk_type_outil_id).where(Thesaurus.code == name).order_by(OutilFacilitateur.nom))]
    return result


@api.put('/pages/<name>')
def update_page(name):
    require_admin()
    result = files.write_page(name, payload(PageSchema())['contenu'])
    from .notifications import page_changed
    result['notification'] = page_changed(name)
    return result


@api.get('/authors')
def authors():
    # Les auteurs connus sont disponibles sans exposer l'annuaire complet.
    prefix = request.args.get('q', '').casefold()
    names = g.db.scalars(select(Animation.auteurs).distinct().order_by(Animation.auteurs))
    return {'items': [name for name in names if name.casefold().startswith(prefix)][:100]}


@api.get('/stats')
def stats():
    dates = []
    day = date.today()
    while day > date(2022, 5, 1):
        dates.append(day)
        day = day.replace(day=1) - timedelta(days=1)
    dates.reverse()
    anims = list(g.db.scalars(select(Animation).where(svc.visible_animations())))
    medias = list(g.db.scalars(select(Media)))
    outils = list(g.db.scalars(select(OutilFacilitateur)))
    def counts(items):
        return [sum(item.date_modif is not None and item.date_modif <= day for item in items) for day in dates]
    return {'dates': [day.isoformat() for day in dates], 'y_anim_all': counts(anims),
            'y_anim_valid': counts([item for item in anims if item.statut == 1]),
            'y_anim_unvalid': counts([item for item in anims if item.statut != 1]),
            'y_mat_peda': counts(medias),
            'y_outil': counts(outils)}


@api.get('/animations/<key>/download')
def export_animation(key):
    item = svc.read_animation(key)
    archive = kit.export_kit(kit.animation_fiche(item))
    return send_file(archive, mimetype='application/zip', as_attachment=True,
                     download_name=kit.safe_name(item.titre, 'animation') + '.zip')


@api.get('/thesaurus/<int:key>/pictogram')
def pictogram(key):
    return send_file(files.pictogram_path(svc.get(Thesaurus, key)), mimetype='image/png', max_age=0)


@api.put('/thesaurus/<int:key>/pictogram')
def put_pictogram(key):
    require_thesaurus_editor()
    item = svc.get(Thesaurus, key)
    file = request.files.get('file')
    if not file:
        raise ValidationError({'file': ['Fichier PNG requis.']})
    files.store_pictogram(item, file)
    return '', 204


@api.delete('/thesaurus/<int:key>/pictogram')
def delete_pictogram(key):
    require_thesaurus_editor()
    files.pictogram_path(svc.get(Thesaurus, key)).unlink()
    return '', 204


@api.get('/users')
def users():
    from .auth import directory_users
    prefix = request.args.get('q', '').strip()
    if not 2 <= len(prefix) <= 100:
        raise ValidationError({'q': ['Saisir entre 2 et 100 caractères.']})
    result = directory_users(prefix)
    if result is None:
        return {'items': authors()['items'], 'source': 'authors'}
    return {'items': result, 'source': 'directory'}
