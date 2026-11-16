"""API JSON version initiale ; toutes les mutations utilisent POST/PUT/DELETE."""
from datetime import date, timedelta
import json

from flask import Blueprint, abort, g, request, session, current_app, send_file
from marshmallow import ValidationError
from sqlalchemy import select, delete, text, or_, func
from sqlalchemy.orm import load_only
from werkzeug.utils import secure_filename

from .auth import authenticate, can_edit_thesaurus, is_admin, login_user, require_admin, require_thesaurus_editor
from .models import (Animation, MatPeda, Thesaurus, Commentaire,
                     RelMatPedaSequence, RelMatPedaThematique, RelAnimTag)
from .schemas import (LoginSchema, AnimationSchema, MaterialSchema, ThesaurusSchema,
                      CommentSchema, PageSchema, AuthorSchema)
from . import services as svc
from . import files
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
                                                 Animation.description, Animation.auteurs)).where(svc.visible_animations()).order_by(Animation.titre, Animation.id)
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
    text_query = request.args.get('q', '').strip()
    if text_query:
        if len(text_query) > 100:
            raise ValidationError({'q': ['100 caractères maximum.']})
        pattern = '%' + text_query.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_') + '%'
        query = query.where(or_(Animation.titre.ilike(pattern, escape='\\'),
                                Animation.description.ilike(pattern, escape='\\')))
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
    items = [{'id': row[0].id, 'titre': row[0].titre, 'statut': row[0].statut,
              'description': row[0].description, 'auteurs': row[0].auteurs,
              'tags': tags_by_anim[row[0].id],
              'pertinence': {'matched': row[1] if tags else 0, 'requested': len(tags)}}
             for row in rows]
    return {'items': items, 'total': total, 'page': page, 'page_size': size}


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


@api.get('/materials')
def materials():
    query = select(MatPeda).order_by(MatPeda.nom, MatPeda.id)
    kind = request.args.get('kind')
    if kind not in (None, 'media', 'outil'):
        raise ValidationError({'kind': ['media ou outil attendu.']})
    if kind:
        query = query.join(Thesaurus, Thesaurus.id == MatPeda.fk_type_mat_id).where(Thesaurus.reference == ('ref.type_mat' if kind == 'media' else 'ref.type_outil'))
    types = id_args('type')
    if types:
        query = query.where(MatPeda.fk_type_mat_id.in_(types))
    if search := request.args.get('q', '').strip()[:100]:
        escaped = search.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')
        query = query.where(MatPeda.nom.ilike(f'%{escaped}%', escape='\\'))
    tags = id_args('tag')
    result = []
    for item in g.db.scalars(query):
        matched = len(tags & {tag.id for tag in item.thematiques})
        if tags and not matched:
            continue
        value = svc.material_dict(item)
        value['pertinence'] = {'matched': matched, 'requested': len(tags)}
        result.append(value)
    if tags:
        result.sort(key=lambda item: -item['pertinence']['matched'])
    return paginate(result)


@api.get('/materials/<int:key>')
def material(key):
    return svc.material_dict(svc.get(MatPeda, key))


@api.post('/materials')
def create_material():
    if request.mimetype == 'multipart/form-data':
        try:
            data = json.loads(request.form.get('data', ''))
        except ValueError:
            raise ValidationError({'data': ['Objet JSON requis.']}) from None
        data = MaterialSchema().load(data)
    else:
        data = payload(MaterialSchema())
    item = svc.save_material(data)
    if file := request.files.get('file'):
        item.url = files.store_upload(file)
    result = svc.material_dict(item)
    g.db.commit()
    return result, 201


@api.put('/materials/<int:key>')
def update_material(key):
    require_admin()
    item = svc.save_material(payload(MaterialSchema()), svc.get(MatPeda, key))
    result = svc.material_dict(item)
    g.db.commit()
    return result


@api.delete('/materials/<int:key>')
def remove_material(key):
    require_admin()
    item = svc.get(MatPeda, key)
    for model in (RelMatPedaSequence, RelMatPedaThematique):
        g.db.execute(delete(model).where(model.fk_mat_peda_id == key))
    g.db.delete(item)
    g.db.commit()
    # Garder les fichiers : d'autres notices peuvent les référencer.
    return '', 204


@api.post('/materials/<int:key>/file')
def upload_material(key):
    require_admin()
    item = svc.get(MatPeda, key)
    file = request.files.get('file')
    if not file:
        abort(422, description='Champ multipart file requis.')
    item.url = files.store_upload(file)
    item.date_modif = date.today()
    g.db.commit()
    return svc.material_dict(item)


@api.get('/materials/<int:key>/preview')
def preview_material(key):
    source, mime = files.preview_file(svc.get(MatPeda, key))
    response = send_file(source, mimetype=mime, download_name='apercu.pdf' if mime == 'application/pdf' else None)
    response.headers['Cache-Control'] = 'no-store'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    return response


@api.get('/materials/<int:key>/thumbnail')
def thumbnail_material(key):
    response = send_file(files.thumbnail_file(svc.get(MatPeda, key)), mimetype='image/jpeg')
    response.headers['Cache-Control'] = 'private, max-age=86400'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    return response


@api.get('/materials/<int:key>/file')
def download_material(key):
    source = files.media_path(svc.get(MatPeda, key))
    return send_file(source, as_attachment=True, download_name=source.name)


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
    fields = MaterialSchema().load({'nom': nom, 'fk_type_mat_id': data.get('fk_type_mat_id'),
                                    'description': f'Crédit : {credit}' if credit else '',
                                    'thematiques': data.get('thematiques', [])})
    item = svc.save_material(fields)
    item.url = files.store_upload(file)
    result = svc.material_dict(item)
    g.db.commit()
    return result, 201


@api.get('/thesaurus')
def thesaurus():
    query = select(Thesaurus).order_by(Thesaurus.label, Thesaurus.id)
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
    item = Thesaurus(**data)
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
    result['documents'] = [svc.material_dict(item) for item in g.db.scalars(select(MatPeda).join(Thesaurus, Thesaurus.id == MatPeda.fk_type_mat_id).where(Thesaurus.reference == 'ref.type_outil', Thesaurus.code == name).order_by(MatPeda.nom))]
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
    mats = list(g.db.scalars(select(MatPeda)))
    def counts(items):
        return [sum(item.date_modif is not None and item.date_modif <= day for item in items) for day in dates]
    return {'dates': [day.isoformat() for day in dates], 'y_anim_all': counts(anims),
            'y_anim_valid': counts([item for item in anims if item.statut == 1]),
            'y_anim_unvalid': counts([item for item in anims if item.statut != 1]),
            'y_mat_peda': counts([item for item in mats if item.fk_type_mat.reference == 'ref.type_mat']),
            'y_outil': counts([item for item in mats if item.fk_type_mat.reference == 'ref.type_outil'])}


@api.get('/animations/<key>/download')
def export_animation(key):
    item = svc.read_animation(key)
    data = svc.animation_dict(item)
    sections = [(name, value) for name, value in data.items() if name not in ('sequences', 'tags')]
    for index, seq in enumerate(item.sequences, 1):
        sections.append((f'Séquence {index} : {seq.titre}', seq.description))
        for name in ('objectifs', 'materiel_div', 'fk_modalite', 'fk_approche', 'duree_minutes', 'fk_type_seq'):
            value = getattr(seq, name)
            sections.append((name, value.label if isinstance(value, Thesaurus) else value))
    sections.append(('Mots-clés', ', '.join(tag.label or '' for tag in item.tags)))
    archive = files.export_archive(item.titre, data, [mat for seq in item.sequences for mat in seq.materiel], sections)
    return send_file(archive, mimetype='application/zip', as_attachment=True, download_name=(secure_filename(item.titre) or 'animation') + '.zip')


@api.get('/materials/<int:key>/download')
def export_tool(key):
    item = svc.get(MatPeda, key)
    data = svc.material_dict(item)
    sections = [(name, value) for name, value in data.items()]
    for name in ('fk_type_mat', 'difficulte', 'fk_type_mat_outil'):
        value = getattr(item, name)
        sections.append((name, value.label if value else ''))
    return send_file(files.export_archive(item.nom, data, [item], sections), mimetype='application/zip',
                     as_attachment=True, download_name=(secure_filename(item.nom) or 'outil') + '.zip')


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
