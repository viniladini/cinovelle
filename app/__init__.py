import secrets

from flask import Flask, abort, g, jsonify, render_template, request, session

from app.config import Config
from app.i18n import translate
from app.integrations import IntegrationError, OMDbClient, TMDBClient
from app.repositories import FavoriteRepository, HistoryRepository, ProfileRepository, TitleRepository, WatchlistRepository
from app.repositories.database import Database
from app.services.catalog import CatalogService
from app.services.recommendation import RecommendationEngine


def create_app(test_config=None):
    app = Flask(__name__)
    app.config.from_object(Config)
    if test_config:
        app.config.update(test_config)
    db = Database(app.config['DATABASE'])
    db.initialize()
    titles = TitleRepository(db)
    tmdb = TMDBClient(app.config['TMDB_API_KEY'], app.config['TMDB_READ_ACCESS_TOKEN'])
    app.extensions['cinovelle'] = {
        'db': db, 'titles': titles, 'profiles': ProfileRepository(db),
        'favorites': FavoriteRepository(db), 'watchlist': WatchlistRepository(db), 'history': HistoryRepository(db),
        'catalog': CatalogService(tmdb, titles, app.config['DEMO_MODE']),
        'engine': RecommendationEngine(version=2), 'omdb': OMDbClient(app.config['OMDB_API_KEY']),
    }

    @app.before_request
    def prepare_request():
        g.services = app.extensions['cinovelle']
        g.language = request.cookies.get('language', 'pt-BR')
        if g.language not in ('pt-BR', 'en-US'):
            g.language = 'pt-BR'
        g.profile = g.services['profiles'].get(session.get('profile_id', 0))
        if 'csrf_token' not in session:
            session['csrf_token'] = secrets.token_hex(24)
        if request.method == 'POST' and not secrets.compare_digest(
            session['csrf_token'], request.form.get('csrf_token', '')):
            abort(400, description='csrf')

    @app.context_processor
    def template_helpers():
        favorites = g.services['favorites'].list(g.profile.id) if g.profile else []
        watchlist = g.services['watchlist'].list(g.profile.id) if g.profile else []
        selected_items = []
        for key in session.get('selection', []):
            try:
                selected_items.append(g.services['catalog'].get(key, g.language))
            except (IntegrationError, LookupError):
                pass
        try:
            available_genres = g.services['catalog'].genres(g.language)
        except IntegrationError:
            available_genres = []
        return dict(t=lambda key: translate(key, g.language), language=g.language, profile=g.profile,
                    demo=g.services['catalog'].demo, favorite_keys={i.key for i in favorites},
                    watchlist_keys={i.key for i in watchlist},
                    imdb_cached=g.services['omdb'].cached_rating,
                    selected_keys=session.get('selection', []),
                    selected_items=selected_items,
                    genres=available_genres,
                    csrf_token=session['csrf_token'])

    @app.errorhandler(IntegrationError)
    def integration_error(error):
        key = error.code if error.code in ('credentials', 'timeout', 'rate_limit', 'not_found') else 'provider_error'
        return error_response(key, 503)

    @app.errorhandler(LookupError)
    def lookup_error(error):
        return error_response('not_found', 404)

    @app.errorhandler(ValueError)
    def validation_error(error):
        key = str(error) if str(error) in ('invalid_name', 'selection_limit', 'invalid_filter') else 'error'
        return error_response(key, 400)

    def error_response(key, code):
        if request.path.startswith('/api/') or request.accept_mimetypes.best == 'application/json':
            return jsonify(message=translate(key, g.language)), code
        return render_template('error.html', message=key), code

    for code, message in [(400, 'error'), (404, 'not_found'), (405, 'method_error'), (413, 'request_large'), (500, 'error')]:
        def handler(error, message=message):
            key = 'csrf' if getattr(error, 'description', '') == 'csrf' else message
            return error_response(key, error.code)
        app.register_error_handler(code, handler)

    from app.routes import web
    app.register_blueprint(web)
    return app
