"""API JSON version initiale ; toutes les mutations utilisent POST/PUT/DELETE."""
from datetime import date, timedelta
import json
import random
from pathlib import Path

from flask import Blueprint, abort, g, jsonify, request, session, current_app, send_file
from marshmallow import ValidationError
from sqlalchemy import select, delete, text, or_, func, String
from sqlalchemy.orm import aliased, load_only, selectinload
from werkzeug.utils import secure_filename

from .auth import authenticate, can_edit_thesaurus, is_admin, login_user, lookup_user, require_admin, require_thesaurus_editor
from .models import (Animation, Media, OutilFacilitateur, Thesaurus, Commentaire,
                     RelMediaSequence, RelMediaThematique, RelAnimTag, RelAnimSequence, RelOutilSequence, Sequence, EvenementUsage)
from .schemas import (LoginSchema, AnimationSchema, SequenceSchema, MediaSchema, OutilSchema, ThesaurusSchema,
                      CommentSchema, PageSchema, AuthorSchema)
from . import oidc
from . import services as svc
from . import files
from . import banners
from . import kit
from . import taxhub
from . import search as finder

api = Blueprint('api', __name__)
MIN_SEARCH_CHARS = 3


def track(kind, resource=None, key=None):
    """Enregistre un événement d'usage ; un échec ne doit jamais bloquer la requête."""
    try:
        g.db.add(EvenementUsage(type=kind, ressource=resource, ressource_id=None if key is None else str(key)))
        g.db.commit()
    except Exception:  # noqa: BLE001
        g.db.rollback()
        current_app.logger.warning('Événement d’usage non enregistré.', exc_info=True)


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


def banner_image(name):
    path = banners.path_of(name)
    if not path:
        abort(404, description='Bannière introuvable.')
    response = send_file(path, mimetype=banners.mime(name))
    response.headers['Cache-Control'] = 'no-cache'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    return response


@api.get('/banners/random')
def random_banner():
    """Bannière de la page d'accueil tirée au hasard, avec sa hauteur de cadrage."""
    names = banners.names()
    if not names:
        abort(404, description='Aucune bannière.')
    name = random.choice(names)
    response = jsonify({'name': name, 'position': banners.position(name)})
    response.headers['Cache-Control'] = 'no-store'
    return response


@api.get('/banners')
def list_banners():
    require_admin()
    return {'items': banners.listing()}


@api.post('/banners')
def add_banner():
    require_admin()
    file = request.files.get('file')
    name = banners.store(file) if file else None
    if not name:
        raise ValidationError({'file': ['Image JPEG, PNG ou WebP requise.']})
    return {'name': name, 'position': 50}, 201


@api.get('/banners/<name>/image')
def banner_file(name):
    return banner_image(name)


@api.put('/banners/<name>')
def update_banner(name):
    require_admin()
    value = (request.get_json(silent=True) or {}).get('position')
    if not banners.path_of(name):
        abort(404, description='Bannière introuvable.')
    if type(value) is not int or not 0 <= value <= 100:
        raise ValidationError({'position': ['Entier entre 0 et 100 requis.']})
    banners.set_position(name, value)
    return {'name': name, 'position': value}


@api.delete('/banners/<name>')
def delete_banner(name):
    require_admin()
    if not banners.path_of(name):
        abort(404, description='Bannière introuvable.')
    banners.remove(name)
    return '', 204


@api.get('/auth/session')
def auth_session():
    user = session.get('user')
    return {'user': user, 'is_admin': is_admin(user), 'can_edit_thesaurus': can_edit_thesaurus(user),
            'csrf_token': session['csrf_token']}


@api.post('/auth/login')
def login():
    if oidc.only_oidc():
        abort(403, description='Connexion par mot de passe désactivée.')
    data = payload(LoginSchema())
    user = authenticate(data['login'].strip(), data['password'])
    if not user:
        abort(401, description='Identifiants invalides.')
    login_user(user)
    track('connexion')
    return auth_session()


@api.get('/auth/oidc/config')
def oidc_config():
    cfg = oidc.settings()
    return {'enabled': oidc.is_enabled(), 'provider': cfg['provider_name'], 'only': oidc.only_oidc()}


@api.get('/auth/oidc/authorize')
def oidc_authorize():
    """URL du fournisseur ; `state` et code_verifier PKCE restent côté navigateur (seule l'empreinte est transmise)."""
    state = request.args.get('state', '')
    challenge = request.args.get('code_challenge', '')
    if not oidc.is_enabled() or not oidc.RE_STATE.match(state) or not oidc.RE_CHALLENGE.match(challenge):
        abort(400, description='Connexion OpenID indisponible.')
    try:
        return {'url': oidc.authorize_url(state, challenge, request.args.get('silent') == '1')}
    except (OSError, ValueError, KeyError):
        abort(503, description='Fournisseur OpenID indisponible.')


@api.post('/auth/oidc/callback')
def oidc_callback():
    data = request.get_json(silent=True)
    data = data if isinstance(data, dict) else {}
    code = data.get('code')
    verifier = data.get('code_verifier')
    if (not oidc.is_enabled() or not isinstance(code, str) or not code or len(code) > 2048
            or not isinstance(verifier, str) or not oidc.RE_VERIFIER.match(verifier)):
        abort(400, description='Connexion OpenID indisponible.')
    try:
        login = oidc.login_from_claims(oidc.exchange_code(code, verifier))
    except oidc.InvalidOidcAuth:
        abort(401, description='Connexion OpenID refusée.')
    except (OSError, ValueError, KeyError):
        abort(503, description='Fournisseur OpenID indisponible.')
    user = lookup_user(login) if login else None
    if not user:
        current_app.logger.warning('Connexion OpenID refusée : aucun compte pour le login reçu.')
        abort(403, description='Votre compte n’a pas été trouvé.')
    login_user(user)
    track('connexion')
    return auth_session()


@api.post('/auth/logout')
def logout():
    session.clear()
    return '', 204


def animation_content_matches(pattern):
    """Le motif figure dans les informations générales, une séquence, un outil ou un média de l'animation."""
    in_sequence = (select(RelAnimSequence.id)
                   .join(Sequence, Sequence.id == RelAnimSequence.fk_sequence_id)
                   .where(RelAnimSequence.fk_anim_id == Animation.id,
                          or_(like(Sequence.titre, pattern), like(Sequence.objectifs, pattern),
                              like(Sequence.description, pattern), like(Sequence.materiel_div, pattern))))
    in_outil = (select(RelOutilSequence.id)
                .join(RelAnimSequence, RelAnimSequence.fk_sequence_id == RelOutilSequence.fk_sequence_id)
                .join(OutilFacilitateur, OutilFacilitateur.id == RelOutilSequence.fk_outil_id)
                .where(RelAnimSequence.fk_anim_id == Animation.id,
                       or_(like(OutilFacilitateur.nom, pattern), like(OutilFacilitateur.description, pattern),
                           like(OutilFacilitateur.variante, pattern), like(OutilFacilitateur.materiel, pattern))))
    in_media = (select(RelMediaSequence.id)
                .join(RelAnimSequence, RelAnimSequence.fk_sequence_id == RelMediaSequence.fk_sequence_id)
                .join(Media, Media.id == RelMediaSequence.fk_media_id)
                .where(RelAnimSequence.fk_anim_id == Animation.id,
                       or_(like(Media.nom, pattern), like(Media.description, pattern))))
    return or_(like(Animation.titre, pattern), like(Animation.description, pattern),
               like(Animation.objectifs, pattern), like(Animation.pre_anim, pattern),
               like(Animation.post_anim, pattern), like(Animation.lieu, pattern),
               like(Animation.public_specifique, pattern), like(Animation.auteurs, pattern),
               in_sequence.exists(), in_outil.exists(), in_media.exists())


def animation_query(deep=False, filtered=True):
    """Requête filtrée de la liste, partagée avec la navigation précédente/suivante.

    `deep` étend la recherche texte à tout le contenu (séquences, outils et médias rattachés) ;
    `filtered=False` ne conserve que la recherche texte et la visibilité (compteurs de la recherche générale).
    """
    query = select(Animation).options(load_only(Animation.id, Animation.titre, Animation.statut,
                                                 Animation.description, Animation.auteurs,
                                                 Animation.objectifs)).where(svc.visible_animations()).order_by(Animation.titre, Animation.id)
    if filtered and 'auteur' in request.args:
        query = query.where(Animation.auteurs == request.args['auteur'])
    statuts = request.args.getlist('statut') if filtered else []
    if statuts:
        try:
            values = {int(value) for value in statuts}
        except ValueError:
            raise ValidationError({'statut': ['Entier requis.']}) from None
        if not values <= {1, 2, 3}:
            raise ValidationError({'statut': ['Valeur hors limites.']})
        query = query.where(Animation.statut.in_(values))
    # Cases cochées en « - » : les animations portant l'un de ces statuts sont écartées.
    excluded_statuts = id_args('non_statut') if filtered else set()
    if excluded_statuts:
        if not excluded_statuts <= {1, 2, 3}:
            raise ValidationError({'non_statut': ['Valeur hors limites.']})
        query = query.where(Animation.statut.not_in(excluded_statuts))
    # Chaque mot de chaque paramètre q est un critère supplémentaire (ET).
    for word in finder.split_terms(request.args.getlist('q')):
        pattern = finder.like_pattern(word)
        if deep:
            query = query.where(animation_content_matches(pattern))
        else:
            query = query.where(or_(like(Animation.titre, pattern), like(Animation.description, pattern),
                                    like(Animation.objectifs, pattern)))
    # Durée cumulée des séquences comprise entre duree_min et duree_max (bornes incluses, en minutes).
    if filtered and ('duree_min' in request.args or 'duree_max' in request.args):
        total = (select(func.coalesce(func.sum(Sequence.duree_minutes), 0))
                 .join(RelAnimSequence, RelAnimSequence.fk_sequence_id == Sequence.id)
                 .where(RelAnimSequence.fk_anim_id == Animation.id).scalar_subquery())
        if 'duree_min' in request.args:
            query = query.where(total >= integer_arg('duree_min', 0, minimum=0, maximum=100000))
        if 'duree_max' in request.args:
            query = query.where(total <= integer_arg('duree_max', 0, minimum=0, maximum=100000))
    tags = id_args('tag') if filtered else []
    if tags:
        counts = (select(RelAnimTag.fk_anim_id, func.count().label('matched'))
                  .where(RelAnimTag.fk_thes_id.in_(tags)).group_by(RelAnimTag.fk_anim_id).subquery())
        query = (query.join(counts, counts.c.fk_anim_id == Animation.id)
                 .order_by(None).order_by(counts.c.matched.desc(), Animation.titre, Animation.id))
        query = query.add_columns(counts.c.matched)
    excluded_tags = id_args('non_tag') if filtered else set()
    if excluded_tags:
        query = query.where(~select(RelAnimTag.id).where(RelAnimTag.fk_anim_id == Animation.id,
                                                          RelAnimTag.fk_thes_id.in_(excluded_tags)).exists())
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


@api.get('/home')
def home():
    """Encarts de la page d'accueil : derniers commentaires et animations, animations à valider (admins)."""
    visible = svc.visible_animations()
    latest = g.db.execute(select(Animation.id, Animation.titre, Animation.description, Animation.auteurs,
                                 Animation.date_modif).where(visible)
                          .order_by(Animation.date_modif.desc().nulls_last(), Animation.titre).limit(1)).first()
    comments_rows = g.db.execute(select(Commentaire.id, Commentaire.date, Commentaire.auteur, Commentaire.commentaire,
                                        Animation.id, Animation.titre)
                                 .join(Animation, Animation.id == Commentaire.fk_id_anim_id).where(visible)
                                 .order_by(Commentaire.date.desc(), Commentaire.id.desc()).limit(5)).all()
    result = {'latest': None if latest is None else {'id': latest[0], 'titre': latest[1], 'description': latest[2],
                                                     'auteurs': latest[3], 'date_modif': latest[4]},
              'comments': [{'id': row[0], 'date': row[1], 'auteur': row[2], 'commentaire': row[3],
                            'animation_id': row[4], 'animation_titre': row[5]} for row in comments_rows],
              'to_validate': None, 'mine': None}
    if g.is_admin:
        pending = select(Animation.id, Animation.titre).where(Animation.statut == 2).order_by(Animation.titre)
        result['to_validate'] = [{'id': row[0], 'titre': row[1]} for row in g.db.execute(pending)]
    else:
        mine = (select(Animation.id, Animation.titre, Animation.statut).where(Animation.auteurs == g.user['name'])
                .order_by(Animation.date_modif.desc().nulls_last(), Animation.titre))
        result['mine'] = [{'id': row[0], 'titre': row[1], 'statut': row[2]} for row in g.db.execute(mine)]
    return result


@api.get('/sequences')
def sequences_list():
    """Séquences des animations visibles, pour en ajouter une copie à une autre animation.

    Filtres : `type` (partie), `approche`, `modalite` (identifiants, OU au sein d'un filtre)
    et `q` répété (ET) sur le titre, les textes et les libellés de référence.
    """
    type_alias, approach_alias, modality_alias = (aliased(Thesaurus) for _ in range(3))
    query = (select(Sequence, Animation.id, Animation.titre)
             .join(RelAnimSequence, RelAnimSequence.fk_sequence_id == Sequence.id)
             .join(Animation, Animation.id == RelAnimSequence.fk_anim_id)
             .join(type_alias, type_alias.id == Sequence.fk_type_seq_id)
             .join(approach_alias, approach_alias.id == Sequence.fk_approche_id)
             .join(modality_alias, modality_alias.id == Sequence.fk_modalite_id)
             .where(svc.visible_animations())
             .order_by(Sequence.titre, Sequence.id))
    for name, column in (('type', Sequence.fk_type_seq_id), ('approche', Sequence.fk_approche_id),
                         ('modalite', Sequence.fk_modalite_id)):
        values = id_args(name)
        if values:
            query = query.where(column.in_(values))
    for pattern, _ in search_terms():
        query = query.where(or_(
            like(Sequence.titre, pattern), like(Sequence.objectifs, pattern),
            like(Sequence.description, pattern), like(Sequence.materiel_div, pattern),
            like(Animation.titre, pattern), like(type_alias.label, pattern),
            like(approach_alias.label, pattern), like(modality_alias.label, pattern)))
    # Les séquences au contenu identique (copies non modifiées) ne sont listées qu'une fois : la plus ancienne.
    content = (Sequence.titre, Sequence.objectifs, Sequence.description, Sequence.materiel_div, Sequence.duree_minutes,
               Sequence.fk_type_seq_id, Sequence.fk_approche_id, Sequence.fk_modalite_id)
    ranked = (query.order_by(None)
              .add_columns(func.row_number().over(partition_by=content, order_by=Sequence.id).label('rank'))
              .subquery())
    unique = (select(ranked.c.id).where(ranked.c.rank == 1).subquery())
    query = (select(Sequence, Animation.id, Animation.titre)
             .join(unique, unique.c.id == Sequence.id)
             .join(RelAnimSequence, RelAnimSequence.fk_sequence_id == Sequence.id)
             .join(Animation, Animation.id == RelAnimSequence.fk_anim_id)
             .order_by(Sequence.titre, Sequence.id))
    total = g.db.scalar(select(func.count()).select_from(unique))
    page = integer_arg('page', 1)
    size = integer_arg('page_size', 20, maximum=200)
    items = []
    for seq, anim_id, anim_title in g.db.execute(query.offset((page - 1) * size).limit(size)):
        value = SequenceSchema(exclude=['materiel', 'outils']).dump(seq)
        value['materiel'] = [mat.id for mat in seq.materiel]
        value['outils'] = [outil.id for outil in seq.outils]
        value['animation'] = {'id': anim_id, 'titre': anim_title}
        items.append(value)
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
    item = svc.read_animation(key)
    result = svc.animation_dict(item)
    track('consultation', 'animation', item.id)
    return result


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
    """Chaque mot de chaque paramètre q est un critère (ET) : renvoie (motif LIKE, motif d'extension) échappés."""
    for word in finder.split_terms(request.args.getlist('q')):
        pattern = finder.like_pattern(word)
        yield pattern, f'%.{pattern[1:-1]}'


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


def filtered_media(filtered=True):
    type_alias = aliased(Thesaurus)
    query = select(Media).outerjoin(type_alias, type_alias.id == Media.fk_type_mat_id).order_by(Media.nom, Media.id)
    types = id_args('type') if filtered else []
    if types:
        query = query.where(Media.fk_type_mat_id.in_(types))
    excluded_types = id_args('non_type') if filtered else set()
    if excluded_types:
        query = query.where(or_(Media.fk_type_mat_id.is_(None), Media.fk_type_mat_id.not_in(excluded_types)))
    for pattern, extension in search_terms():
        theme_alias = aliased(Thesaurus)
        theme = (select(RelMediaThematique.id)
                 .join(theme_alias, theme_alias.id == RelMediaThematique.fk_thes_id)
                 .where(RelMediaThematique.fk_media_id == Media.id, like(theme_alias.label, pattern)))
        query = query.where(or_(like(Media.nom, pattern), like(Media.description, pattern),
                                like(Media.url, extension), like(type_alias.label, pattern), theme.exists()))
    tags = set(id_args('tag')) if filtered else set()
    excluded_tags = id_args('non_tag') if filtered else set()
    result = []
    for item in g.db.scalars(query):
        item_tags = {tag.id for tag in item.thematiques}
        if excluded_tags & item_tags:
            continue
        matched = len(tags & item_tags)
        if tags and not matched:
            continue
        value = svc.media_dict(item)
        value['pertinence'] = {'matched': matched, 'requested': len(tags)}
        result.append(value)
    if tags:
        result.sort(key=lambda item: -item['pertinence']['matched'])
    return result


@api.get('/media')
def media_list():
    return paginate(filtered_media())


@api.get('/media/<int:key>/neighbors')
def media_neighbors(key):
    """Médias voisins de `key` dans la liste filtrée (mêmes paramètres que /media)."""
    rows = [item['id'] for item in filtered_media()]
    if key not in rows:
        return {'found': False, 'previous': None, 'next': None, 'position': None, 'total': len(rows)}
    position = rows.index(key)
    return {'found': True, 'position': position + 1, 'total': len(rows),
            'previous': rows[position - 1] if position > 0 else None,
            'next': rows[position + 1] if position + 1 < len(rows) else None}


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


def filtered_outils(filtered=True):
    type_alias, difficulty_alias, media_alias = (aliased(Thesaurus) for _ in range(3))
    query = (select(OutilFacilitateur)
             .outerjoin(type_alias, type_alias.id == OutilFacilitateur.fk_type_outil_id)
             .outerjoin(difficulty_alias, difficulty_alias.id == OutilFacilitateur.difficulte_id)
             .outerjoin(media_alias, media_alias.id == OutilFacilitateur.fk_type_mat_outil_id)
             .order_by(OutilFacilitateur.nom, OutilFacilitateur.id))
    types = id_args('type') if filtered else []
    if types:
        query = query.where(OutilFacilitateur.fk_type_outil_id.in_(types))
    excluded_types = id_args('non_type') if filtered else set()
    if excluded_types:
        query = query.where(or_(OutilFacilitateur.fk_type_outil_id.is_(None),
                                OutilFacilitateur.fk_type_outil_id.not_in(excluded_types)))
    difficulties = id_args('difficulte') if filtered else []
    if difficulties:
        query = query.where(OutilFacilitateur.difficulte_id.in_(difficulties))
    excluded_difficulties = id_args('non_difficulte') if filtered else set()
    if excluded_difficulties:
        query = query.where(or_(OutilFacilitateur.difficulte_id.is_(None),
                                OutilFacilitateur.difficulte_id.not_in(excluded_difficulties)))
    for pattern, extension in search_terms():
        query = query.where(or_(
            like(OutilFacilitateur.nom, pattern), like(OutilFacilitateur.description, pattern),
            like(OutilFacilitateur.variante, pattern), like(OutilFacilitateur.materiel, pattern),
            like(OutilFacilitateur.url, extension), like(type_alias.label, pattern),
            like(difficulty_alias.label, pattern), like(media_alias.label, pattern)))
    return [svc.outil_dict(item) for item in g.db.scalars(query)]


@api.get('/outils')
def outils_list():
    return paginate(filtered_outils())


SEARCH_KINDS = ('animations', 'outils', 'media')


def animation_fields(item, start=''):
    """Contenus consultables d'une animation, avec leur provenance, pour les extraits de recherche.

    `start` : début de la description, déjà affiché et donc exclu des extraits.
    """
    fields = [('Description', finder.after_start(item.description, start)), ('Objectifs', item.objectifs),
              ('Avant l’animation', item.pre_anim), ('Après l’animation', item.post_anim),
              ('Lieu', item.lieu), ('Public spécifique', item.public_specifique), ('Auteurs', item.auteurs)]
    for seq in item.sequences:
        label = f'Séquence « {seq.titre} »'
        fields += [(label, seq.titre), (f'{label} · Déroulement', seq.description),
                   (f'{label} · Objectifs', seq.objectifs), (f'{label} · Matériel complémentaire', seq.materiel_div)]
        for tool in seq.outils:
            label = f'Outil facilitateur « {tool.nom} »'
            fields += [(label, tool.nom), (f'{label} · Description', tool.description),
                       (f'{label} · Variante', tool.variante), (f'{label} · Matériel', tool.materiel)]
        for medium in seq.materiel:
            label = f'Média « {medium.nom} »'
            fields += [(label, medium.nom), (f'{label} · Description', medium.description)]
    return fields


def search_animations(terms):
    query, _ = animation_query(deep=True)
    page = integer_arg('page', 1)
    size = integer_arg('page_size', 20, maximum=100)
    total = g.db.scalar(select(func.count()).select_from(query.order_by(None).subquery()))
    keys = [row[0].id for row in g.db.execute(query.offset((page - 1) * size).limit(size))]
    loaded = {}
    if keys:
        full = (select(Animation).where(Animation.id.in_(keys))
                .options(selectinload(Animation.sequences).selectinload(Sequence.materiel),
                         selectinload(Animation.sequences).selectinload(Sequence.outils)))
        loaded = {item.id: item for item in g.db.scalars(full)}
    tags_by_anim = {key: [] for key in keys}
    if keys:
        for anim_id, tag_id in g.db.execute(select(RelAnimTag.fk_anim_id, RelAnimTag.fk_thes_id)
                                            .where(RelAnimTag.fk_anim_id.in_(keys)).order_by(RelAnimTag.id)):
            tags_by_anim[anim_id].append(tag_id)
    items = []
    for key in keys:
        item = loaded[key]
        start = finder.first_lines(item.description)
        items.append({'id': item.id, 'titre': item.titre, 'statut': item.statut, 'auteurs': item.auteurs,
                      'tags': tags_by_anim[key], 'fk_duree_id': item.fk_duree_id, 'debut': start,
                      'extraits': finder.build_snippets(animation_fields(item, start), terms)})
    return {'items': items, 'total': total, 'page': page, 'page_size': size}


def search_listed(items, fields, terms, start=False):
    """Pagine une liste déjà filtrée et y joint les extraits : `fields(item)` donne les (source, contenu)."""
    result = paginate(items)
    for item in result['items']:
        if start:  # `debut` : premières lignes de la description, toujours affichées
            item['debut'] = finder.first_lines(item['description'])
        item['extraits'] = finder.build_snippets(fields(item), terms)
    return result


@api.get('/search')
def general_search():
    """Recherche générale (ET entre les mots) dans la pédathèque, les outils facilitateurs et la médiathèque.

    `kind` choisit l'onglet détaillé et ses filtres (mêmes paramètres que /animations, /outils et /media) ;
    `counts` donne le nombre de résultats de chaque onglet pour la seule recherche texte.
    """
    terms = finder.split_terms(request.args.getlist('q'))
    kind = request.args.get('kind', 'animations')
    if kind not in SEARCH_KINDS:
        raise ValidationError({'kind': ['Valeur hors limites.']})
    if not terms:
        return {'terms': [], 'kind': kind, 'items': [], 'total': 0, 'page': 1, 'page_size': 20,
                'counts': dict.fromkeys(SEARCH_KINDS, 0)}
    unfiltered, _ = animation_query(deep=True, filtered=False)
    counts = {'animations': g.db.scalar(select(func.count()).select_from(unfiltered.order_by(None).subquery())),
              'outils': len(filtered_outils(filtered=False)), 'media': len(filtered_media(filtered=False))}
    if kind == 'animations':
        result = search_animations(terms)
    elif kind == 'outils':
        result = search_listed(filtered_outils(), lambda item: [
            ('Description', finder.after_start(item['description'], item['debut'])),
            ('Variante', item['variante']), ('Matériel', item['materiel'])], terms, start=True)
    else:
        result = search_listed(filtered_media(), lambda item: [('Description', item['description'])], terms)
    return {**result, 'terms': terms, 'kind': kind, 'counts': counts}


@api.get('/outils/<int:key>/neighbors')
def outil_neighbors(key):
    """Outils voisins de `key` dans la liste filtrée (mêmes paramètres que /outils)."""
    rows = [(item['id'], item['nom']) for item in filtered_outils()]
    position = next((index for index, row in enumerate(rows) if row[0] == key), None)
    if position is None:
        return {'found': False, 'previous': None, 'next': None, 'position': None, 'total': len(rows)}

    def brief(row):
        return {'id': row[0], 'nom': row[1]} if row else None
    return {'found': True, 'position': position + 1, 'total': len(rows),
            'previous': brief(rows[position - 1] if position > 0 else None),
            'next': brief(rows[position + 1] if position + 1 < len(rows) else None)}


@api.get('/outils/<int:key>')
def outil(key):
    item = svc.get(OutilFacilitateur, key)
    result = svc.outil_dict(item)
    track('consultation', 'outil', item.id)
    return result


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
    item = svc.get(OutilFacilitateur, key)
    g.db.execute(delete(RelOutilSequence).where(RelOutilSequence.fk_outil_id == key))
    g.db.delete(item)
    g.db.commit()
    # Garder les fichiers : d'autres notices peuvent les référencer.
    return '', 204


@api.post('/outils/<int:key>/file')
def upload_outil(key):
    require_admin()
    return svc.outil_dict(upload_file(svc.get(OutilFacilitateur, key)))


@api.get('/outils/<int:key>/preview')
def preview_outil(key):
    source, mime = files.preview_file(svc.get(OutilFacilitateur, key), native=request.args.get('natif') == '1')
    response = send_file(source, mimetype=mime, download_name='apercu.pdf' if mime == 'application/pdf' else None)
    response.headers['Cache-Control'] = 'no-store'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    return response


@api.get('/outils/<int:key>/thumbnail')
def thumbnail_outil(key):
    response = send_file(files.thumbnail_file(svc.get(OutilFacilitateur, key)), mimetype='image/jpeg')
    response.headers['Cache-Control'] = 'private, max-age=86400'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    return response


@api.get('/outils/<int:key>/file')
def download_outil(key):
    item = svc.get(OutilFacilitateur, key)
    source = files.media_path(item)
    track('telechargement', 'outil', item.id)
    return send_file(source, as_attachment=True, download_name=source.name)


@api.get('/outils/<int:key>/download')
def export_outil(key):
    item = svc.get(OutilFacilitateur, key)
    archive = kit.export_kit(kit.outil_fiche(item))
    track('telechargement', 'outil', item.id)
    return send_file(archive, mimetype='application/zip', as_attachment=True,
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


@api.get('/files/config')
def files_config():
    """Extensions de fichier acceptées au téléversement (pour prévenir l'utilisateur avant l'envoi)."""
    return {'allowed_extensions': sorted(current_app.extensions['settings']['backend']['allowed_extensions'])}


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


def usage_stats(dates):
    """Connexions mensuelles et classements des animations et outils les plus consultés/téléchargés."""
    month = func.date_trunc('month', EvenementUsage.date) if g.db.bind.dialect.name == 'postgresql' \
        else func.strftime('%Y-%m-01', EvenementUsage.date)
    rows = g.db.execute(select(month, func.count()).where(EvenementUsage.type == 'connexion').group_by(month))
    per_month = {str(row[0])[:7]: row[1] for row in rows}
    result = {'connexions': [per_month.get(day.isoformat()[:7], 0) for day in dates]}
    models = {'animation': (Animation, Animation.titre), 'outil': (OutilFacilitateur, OutilFacilitateur.nom)}
    for resource, (model, label) in models.items():
        for kind, name in (('consultation', 'consultes'), ('telechargement', 'telecharges')):
            total = func.count(EvenementUsage.id)
            query = (select(model.id, label, total)
                     .join(EvenementUsage, (EvenementUsage.ressource == resource)
                           & (EvenementUsage.ressource_id == func.cast(model.id, String(40)))
                           & (EvenementUsage.type == kind)))
            if resource == 'animation':
                query = query.where(svc.visible_animations())
            query = query.group_by(model.id, label).order_by(total.desc(), label).limit(10)
            result[f'top_{resource}_{name}'] = [{'id': row[0], 'titre': row[1], 'total': row[2]}
                                                for row in g.db.execute(query)]
    return result


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
            'y_outil': counts(outils), **usage_stats(dates)}


@api.get('/animations/<key>/download')
def export_animation(key):
    item = svc.read_animation(key)
    archive = kit.export_kit(kit.animation_fiche(item))
    track('telechargement', 'animation', item.id)
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
