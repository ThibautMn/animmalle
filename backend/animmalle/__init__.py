"""Fabrique Flask ; aucun accès à la base lors de l'import."""
from datetime import timedelta

from flask import Flask, g, jsonify, request
from marshmallow import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from werkzeug.exceptions import HTTPException, RequestEntityTooLarge
from werkzeug.middleware.proxy_fix import ProxyFix

from .config import CONFIG_PATH, load_database_url, load_settings


def create_app(config_path=CONFIG_PATH, *, engine=None):
    settings = load_settings(config_path)
    app = Flask(__name__, static_folder=None)
    cfg = settings['backend']
    app.config.update(SECRET_KEY=cfg['secret_key'], SESSION_COOKIE_NAME='animmalle_session',
                      SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SECURE=cfg['cookie_secure'],
                      SESSION_COOKIE_SAMESITE=cfg['cookie_samesite'],
                      PERMANENT_SESSION_LIFETIME=timedelta(hours=cfg['session_hours']),
                      MAX_CONTENT_LENGTH=cfg['max_upload_mb'] * 1024 * 1024)
    app.extensions['settings'] = settings
    db_engine = engine if engine is not None else create_engine(load_database_url(config_path), pool_pre_ping=True, hide_parameters=True)
    app.extensions['db_engine'] = db_engine
    app.extensions['db_sessions'] = sessionmaker(db_engine, expire_on_commit=False)
    app.wsgi_app = ProxyFix(app.wsgi_app, **settings['proxy'])

    @app.before_request
    def open_session():
        g.db = app.extensions['db_sessions']()

    @app.teardown_request
    def close_session(error):
        if 'db' in g:
            g.db.rollback()
            g.db.close()

    @app.errorhandler(ValidationError)
    def validation_error(error):
        return jsonify(error={'code': 'validation', 'message': 'Données invalides.', 'fields': error.messages}), 422

    @app.errorhandler(IntegrityError)
    def integrity_error(error):
        g.db.rollback()
        return jsonify(error={'code': 'conflict', 'message': 'Valeur déjà utilisée ou élément encore référencé.'}), 409

    @app.errorhandler(SQLAlchemyError)
    def database_error(error):
        g.db.rollback()
        return jsonify(error={'code': 'database', 'message': 'Base de données indisponible.'}), 503

    @app.errorhandler(RequestEntityTooLarge)
    def too_large(error):
        limit = app.config['MAX_CONTENT_LENGTH'] // (1024 * 1024)
        return jsonify(error={'code': '413', 'message': f'Fichier trop volumineux (limite : {limit} Mo).'}), 413

    @app.errorhandler(HTTPException)
    def http_error(error):
        return jsonify(error={'code': str(error.code), 'message': error.description}), error.code

    @app.errorhandler(Exception)
    def unexpected_error(error):
        # Ne pas journaliser la requête, les paramètres SQL ou l'exception brute.
        app.logger.error('Erreur interne backend (%s).', type(error).__name__)
        return jsonify(error={'code': 'internal', 'message': 'Erreur interne.'}), 500

    @app.after_request
    def headers(response):
        origin = request.headers.get('Origin')
        if origin == settings['public']['frontend_url'].rstrip('/'):
            response.headers['Access-Control-Allow-Origin'] = origin
            response.headers['Access-Control-Allow-Credentials'] = 'true'
            response.headers['Access-Control-Expose-Headers'] = 'Content-Disposition'
            response.headers['Access-Control-Allow-Headers'] = 'Content-Type, X-CSRF-Token'
            response.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS'
            response.vary.add('Origin')
        # Seules les vignettes (cache privé explicite) échappent à no-store.
        if not response.headers.get('Cache-Control', '').startswith('private, max-age='):
            response.headers['Cache-Control'] = 'no-store'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        return response

    from .auth import install_auth
    from .routes import api
    install_auth(app)
    app.register_blueprint(api, url_prefix='/api')
    return app
