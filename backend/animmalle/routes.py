"""API JSON version initiale ; toutes les mutations utilisent POST/PUT/DELETE."""
from datetime import date, timedelta
import json

from flask import Blueprint, abort, g, request, session, current_app, send_file
from marshmallow import ValidationError
from sqlalchemy import select, delete, text
from werkzeug.utils import secure_filename

from .auth import authenticate, login_user, require_admin
from .models import (Animation, MatPeda, Thesaurus, Commentaire,
                     RelMatPedaSequence, RelMatPedaThematique)
from .schemas import (LoginSchema, AnimationSchema, MaterialSchema, ThesaurusSchema,
                      CommentSchema, PageSchema, AuthorSchema)
from . import services as svc
from . import files

api = Blueprint('api', __name__)


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
    return {'user': user, 'is_admin': bool(user and set(user['groups']) & set(current_app.extensions['settings']['auth']['admin_groups'])),
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


@api.get('/animations')
def animations():
    query = select(Animation).where(svc.visible_animations()).order_by(Animation.titre, Animation.id)
    if 'auteur' in request.args:
        query = query.where(Animation.auteurs == request.args['auteur'])
    if 'statut' in request.args:
        query = query.where(Animation.statut == integer_arg('statut', 1, maximum=3))
    tags = id_args('tag')
    results = []
    for item in g.db.scalars(query):
        matched = len(tags & {tag.id for tag in item.tags})
        if tags and not matched:
            continue
        value = svc.animation_dict(item)
        value['pertinence'] = {'matched': matched, 'requested': len(tags)}
        results.append(value)
    if tags:
        results.sort(key=lambda item: -item['pertinence']['matched'])
    return paginate(results)


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


@api.get('/materials/<int:key>/file')
def download_material(key):
    source = files.media_path(svc.get(MatPeda, key))
    return send_file(source, as_attachment=True, download_name=source.name)


@api.get('/thesaurus')
def thesaurus():
    query = select(Thesaurus).order_by(Thesaurus.label, Thesaurus.id)
    if 'reference' in request.args:
        query = query.where(Thesaurus.reference == request.args['reference'])
    return {'items': ThesaurusSchema(many=True).dump(g.db.scalars(query))}


@api.post('/thesaurus')
def create_tag():
    require_admin()
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


@api.delete('/thesaurus/<int:key>')
def remove_tag(key):
    require_admin()
    item = svc.get(Thesaurus, key)
    if item.reference == '' and g.db.scalar(select(Thesaurus.id).where(Thesaurus.reference == item.code)):
        abort(409, description='Catégorie encore utilisée.')
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
        for name in ('objectifs', 'materiel_div', 'fk_modalite', 'fk_approche', 'fk_duree', 'fk_type_seq'):
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
    item = svc.get(Thesaurus, key)
    if item.reference not in ('ref.thematiques', 'ref.lieux', 'ref.saison'):
        abort(404)
    root = files.paths()['pictograms']
    source = (root / ((item.label or '') + '.png')).resolve()
    if not source.is_relative_to(root) or not source.is_file():
        abort(404)
    return send_file(source, mimetype='image/png')


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
