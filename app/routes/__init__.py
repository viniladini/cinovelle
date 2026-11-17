from flask import Blueprint, abort, flash, g, jsonify, make_response, redirect, render_template, request, session, url_for

from app.integrations import IntegrationError
from app.i18n import translate

web = Blueprint('web', __name__)


def service(name):
    return g.services[name]


def wants_json():
    return request.accept_mimetypes.best == 'application/json'


def item_data(item):
    return {'key': item.key, 'title': item.title, 'year': item.year, 'poster': item.poster,
            'media_type': item.media_type, 'media_label': translate(item.media_type, g.language)}


@web.get('/api/search')
def search_suggestions():
    query = request.args.get('q', '').strip()[:120]
    kind = request.args.get('type', 'both')
    if kind not in ('both', 'movie', 'tv'):
        raise ValueError('invalid_filter')
    items = service('catalog').search(query, g.language, kind)[:8] if len(query) >= 2 else []
    favorite_keys = {item.key for item in service('favorites').list(g.profile.id)} if g.profile else set()
    response = jsonify(items=[{**item_data(item), 'selected': item.key in session.get('selection', []),
                                'favorite': item.key in favorite_keys} for item in items])
    response.headers['Cache-Control'] = 'no-store'
    return response


@web.get('/api/title/<key>/providers')
def watch_providers(key):
    return jsonify(service('catalog').watch_providers(key, g.language))


def require_profile():
    if not g.profile:
        flash('need_profile')
        return redirect(url_for('web.profiles'))


def genres():
    try:
        return service('catalog').genres(g.language)
    except IntegrationError:
        flash('provider_error')
        return []


def selection():
    return [service('catalog').get(key, g.language) for key in session.get('selection', [])]


@web.get('/')
@web.get('/explore', endpoint='explore')
def home():
    query = request.args.get('q', '').strip()[:120]
    kind = request.args.get('type', 'both')
    if kind not in ('both', 'movie', 'tv'):
        raise ValueError('invalid_filter')
    try:
        items = service('catalog').search(query, g.language, kind)
    except IntegrationError as error:
        flash(error.code if error.code in ('credentials', 'timeout', 'rate_limit') else 'provider_error')
        items = []
    genre = request.args.get('genre', '')
    try:
        genre_id = int(genre) if genre else None
    except ValueError:
        raise ValueError('invalid_filter') from None
    if genre_id:
        items = [item for item in items if genre_id in item.genre_ids()]
    featured = next((item for item in items if item.media_type == 'movie' and item.backdrop),
                    next((item for item in items if item.media_type == 'movie'), items[0] if items else None))
    personal = []
    if not query and g.profile and g.profile.preferences:
        personal = [item for item in items if item.genre_ids().intersection(g.profile.preferences)]
    highlights = [featured] if featured else []
    movies = [item for item in items if item.media_type == 'movie' and item != featured]
    series = [item for item in items if item.media_type == 'tv' and item != featured]
    for index in range(max(len(movies), len(series))):
        for values in (series, movies):
            if index < len(values) and len(highlights) < 6:
                highlights.append(values[index])
    return render_template('home.html', items=items, query=query, kind=kind, selected=selection(),
                           genres=genres(), featured=featured, highlights=highlights, personal=personal,
                           explore=request.endpoint == 'web.explore', genre_id=genre_id)


@web.post('/selection')
def select():
    key = request.form.get('key', '')
    current = session.get('selection', []).copy()
    if request.form.get('action') == 'remove':
        current = [item for item in current if item != key]
    elif key not in current:
        if len(current) >= 5:
            raise ValueError('selection_limit')
        service('catalog').get(key, g.language)
        current.append(key)
    session['selection'] = current
    if wants_json():
        return jsonify(selected=[item_data(item) for item in selection()], message=translate('updated', g.language))
    return redirect(url_for('web.home', q=request.form.get('q', ''), _anchor='discovery'))


@web.post('/recommendations')
def recommendations():
    seeds = selection()
    if not 1 <= len(seeds) <= 5:
        raise ValueError('selection_limit')
    kind = request.form.get('type', 'both')
    if kind not in ('both', 'movie', 'tv'):
        raise ValueError('invalid_filter')
    genre = request.form.get('genre', '')
    try:
        genre_id = int(genre) if genre else None
    except ValueError:
        raise ValueError('invalid_filter') from None
    use_preferences = request.form.get('preferences') == 'on'
    preferences = g.profile.preferences if use_preferences and g.profile else []
    results = service('engine').discover(service('catalog'), seeds, g.language, kind, genre_id, preferences)
    if g.profile:
        service('history').create(g.profile.id, [{'key': i.key, 'title': i.title} for i in seeds],
                                  {'type': kind, 'genre': genre_id, 'preferences': preferences},
                                  service('engine').displayable(results), service('titles'))
    return render_template('results.html', results=results, seeds=seeds, genres=genres(),
                           kind=kind, genre_id=genre_id, use_preferences=use_preferences)


@web.post('/similar/<key>')
def similar(key):
    seed = service('catalog').get(key, g.language)
    results = service('engine').discover(service('catalog'), [seed], g.language)
    if g.profile:
        service('history').create(g.profile.id, [{'key': seed.key, 'title': seed.title}],
                                  {'type': 'both', 'genre': None, 'preferences': []},
                                  service('engine').displayable(results), service('titles'))
    return render_template('results.html', results=results, seeds=[seed], genres=genres(),
                           kind='both', genre_id=None, use_preferences=False)


@web.get('/title/<key>')
def details(key):
    item = service('catalog').get(key, g.language)
    imdb = None
    try:
        if service('omdb').configured:
            service('catalog').ensure_imdb_id(item, g.language)
        imdb = service('omdb').rating(item.imdb_id)
    except IntegrationError:
        flash('provider_error')
    # Recomendações completas são calculadas sob demanda para evitar dezenas de consultas nos detalhes.
    try:
        candidates = service('catalog').search('', g.language) if item.source != 'demo' else service('catalog').candidates([item], g.language)[0]
        related = service('engine').displayable(service('engine').recommend([item], candidates))[:4]
    except IntegrationError:
        related = []
    return render_template('details.html', item=item, imdb=imdb, related=related)


@web.get('/profiles')
def profiles():
    return render_template('profiles.html', profiles=service('profiles').all())


@web.post('/profiles')
def create_profile():
    profile = service('profiles').create(request.form.get('name', ''))
    session['profile_id'] = profile.id
    session.pop('selection', None)
    flash('profile_created')
    return redirect(url_for('web.taste'))


@web.post('/profiles/<int:profile_id>/<action>')
def profile_action(profile_id, action):
    if not service('profiles').get(profile_id):
        abort(404)
    if action == 'enter':
        session['profile_id'] = profile_id
        session.pop('selection', None)
        return redirect(url_for('web.home'))
    if action == 'delete':
        service('profiles').delete(profile_id)
        if session.get('profile_id') == profile_id:
            session.pop('profile_id', None)
            session.pop('selection', None)
        flash('deleted')
        return redirect(url_for('web.profiles'))
    abort(404)


@web.post('/logout')
def logout():
    session.pop('profile_id', None)
    session.pop('selection', None)
    return redirect(url_for('web.profiles'))


@web.get('/taste')
def taste():
    guard = require_profile()
    if guard:
        return guard
    return render_template('taste.html', genres=genres(), runs=service('history').list(g.profile.id))


@web.post('/taste')
def update_taste():
    guard = require_profile()
    if guard:
        return guard
    allowed = {genre.id for genre in genres()}
    try:
        preferences = sorted({int(value) for value in request.form.getlist('genres')})
    except ValueError:
        raise ValueError('invalid_filter') from None
    if not set(preferences) <= allowed:
        raise ValueError('invalid_filter')
    service('profiles').update(g.profile.id, request.form.get('name', ''), preferences)
    flash('updated')
    return redirect(url_for('web.taste'))


@web.get('/favorites')
def favorites():
    guard = require_profile()
    if guard:
        return guard
    return render_template('favorites.html', items=service('favorites').list(g.profile.id))


@web.post('/favorites')
def toggle_favorite():
    if wants_json() and not g.profile:
        return jsonify(message=translate('need_profile', g.language)), 401
    guard = require_profile()
    if guard:
        return guard
    item = service('catalog').get(request.form.get('key', ''), g.language)
    title_id = service('titles').save(item)
    if request.form.get('action') == 'remove':
        service('favorites').remove(g.profile.id, title_id)
    else:
        service('favorites').add(g.profile.id, title_id)
    if wants_json():
        return jsonify(key=item.key, favorite=request.form.get('action') != 'remove',
                       message=translate('updated', g.language))
    flash('updated')
    if request.form.get('return_to') == 'favorites':
        return redirect(url_for('web.favorites'))
    return redirect(url_for('web.details', key=item.key))


@web.get('/watchlist')
def watchlist():
    guard = require_profile()
    if guard:
        return guard
    return render_template('watchlist.html', items=service('watchlist').list(g.profile.id))


@web.post('/watchlist')
def toggle_watchlist():
    if wants_json() and not g.profile:
        return jsonify(message=translate('need_profile', g.language)), 401
    guard = require_profile()
    if guard:
        return guard
    item = service('catalog').get(request.form.get('key', ''), g.language)
    title_id = service('titles').save(item)
    active = request.form.get('action') != 'remove'
    if active:
        service('watchlist').add(g.profile.id, title_id)
    else:
        service('watchlist').remove(g.profile.id, title_id)
    if wants_json():
        return jsonify(key=item.key, watchlist=active, message=translate('updated', g.language))
    return redirect(url_for('web.watchlist'))


@web.post('/history/delete')
def delete_history():
    guard = require_profile()
    if guard:
        return guard
    value = request.form.get('run_id', '')
    service('history').delete(g.profile.id, int(value) if value else None)
    flash('deleted')
    return redirect(url_for('web.taste'))


@web.post('/language/<language>')
def language(language):
    if language not in ('pt-BR', 'en-US'):
        abort(404)
    response = make_response(redirect(url_for('web.home')))
    response.set_cookie('language', language, max_age=365 * 86400, httponly=True, samesite='Lax')
    return response
