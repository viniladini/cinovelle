from app.models import Genre, Movie, TVSeries
from app.services.themes import concepts, profile, narrative_terms
from app.services.recommendation import RecommendationEngine


def film(value, labels, genres=(18,), tv=False):
    cls = TVSeries if tv else Movie
    names = {str(index): name for index, name in enumerate(labels, 100 * value)}
    return cls(value, str(value), genres=[Genre(g, str(g)) for g in genres], keywords=set(names), keyword_names=names)


def test_bilingual_concepts_only_follow_observed_metadata():
    assert concepts('psychological thriller family relationships social commentary supernatural') == {
        'psychological', 'family', 'social', 'supernatural'}
    assert concepts('suspense psicológico família crítica social sobrenatural') == {
        'psychological', 'family', 'social', 'supernatural'}
    assert profile(Movie(1, 'Empty', genres=[Genre(18, 'Drama')])) == {}
    assert concepts('ordinary description about trees') == set()
    assert 'family' not in concepts('Um país estrangeiro.')
    assert not (narrative_terms('Uma cientista com sua família procura uma resposta').keys()
                & narrative_terms('The scientist with her family searches for an answer').keys())


def test_combined_profile_connects_independent_reference_features_and_is_explained():
    a = film(1, ['psychological thriller', 'family', 'social commentary'], (27, 53))
    b = film(2, ['family relationships', 'mystery', 'supernatural'], (16, 9648))
    c = film(3, ['social criticism', 'con artist', 'family'], (18, 35))
    bridge = film(4, ['family', 'psychological horror', 'identity', 'social commentary', 'supernatural'], (27, 53))
    unrelated = film(5, ['space travel', 'scientist', 'quantum mechanics'], (878,))
    engine = RecommendationEngine(version=2)
    rows = engine.recommend([a, b, c], [bridge, unrelated])
    row = next(row for row in rows if row.item.key == bridge.key)
    assert row.factors['reference_count'] == 3
    assert row.factors['shared_concepts'] >= 2
    assert 'reason_combined' in row.explanation_keys
    assert row.is_relevant
    assert not next(row for row in rows if row.item.key == unrelated.key).is_relevant
    assert [(r.item.key, r.score) for r in rows] == [(r.item.key, r.score) for r in engine.recommend([c, b, a], [unrelated, bridge])]


def test_different_interest_group_is_preserved_and_rating_does_not_set_match():
    a = film(1, ['space travel', 'science', 'time travel'], (878, 12))
    b = film(2, ['romance', 'family relationships'], (10749, 35))
    candidate = film(3, ['space travel', 'scientist', 'time travel'], (878, 12), tv=True)
    engine = RecommendationEngine(version=2)
    single = engine.recommend([a], [candidate])[0]
    combined = engine.recommend([a, b], [candidate])[0]
    assert combined.score >= single.score
    candidate.rating = 10
    assert engine.recommend([a, b], [candidate])[0].score == combined.score


def test_rank_and_single_display_list_keep_all_relevant_scores():
    from app.models import Recommendation
    rows = [Recommendation(Movie(i, str(i)), score, {'relevant_evidence': relevant}, [])
            for i, score, relevant in [(1, 69, 1), (2, 90, 1), (3, 20, 1), (4, 80, 0)]]
    visible = RecommendationEngine.displayable(rows)
    assert [row.score for row in visible] == [90, 69, 20]


def test_watchlist_crud_isolation_restart_and_profile_cascade(app, client, post, services):
    from app import create_app
    headers = {'Accept': 'application/json'}
    assert post('/watchlist', {'key': 'demo:movie:1'}, headers=headers).status_code == 401
    post('/profiles', {'name': 'A'})
    for _ in range(2):
        assert post('/watchlist', {'key': 'demo:movie:1'}, headers=headers).json['watchlist']
    assert len(services['watchlist'].list(1)) == 1
    assert services['favorites'].list(1) == []
    assert 'Depois da última sessão' in client.get('/watchlist').text
    assert len(create_app(dict(app.config)).extensions['cinovelle']['watchlist'].list(1)) == 1
    post('/profiles', {'name': 'B'})
    assert services['watchlist'].list(2) == []
    post('/watchlist', {'key': 'demo:movie:1', 'action': 'remove'}, headers=headers)
    assert len(services['watchlist'].list(1)) == 1
    post('/profiles/1/enter')
    assert not post('/watchlist', {'key': 'demo:movie:1', 'action': 'remove'}, headers=headers).json['watchlist']
    post('/watchlist', {'key': 'demo:tv:3'}, headers=headers)
    post('/profiles/1/delete')
    with services['db'].connection() as conn:
        assert conn.execute('SELECT COUNT(*) FROM watchlist').fetchone()[0] == 0
        assert conn.execute('PRAGMA foreign_key_check').fetchall() == []
    assert client.post('/watchlist', data={'key': 'demo:movie:1'}, headers=headers).status_code == 400


def test_watchlist_migration_keeps_existing_database_data(services):
    profile = services['profiles'].create('Before')
    with services['db'].connection() as conn:
        conn.execute('DROP TABLE watchlist')
    services['db'].initialize()
    services['db'].initialize()
    assert services['profiles'].get(profile.id).name == 'Before'
    with services['db'].connection() as conn:
        assert conn.execute('SELECT COUNT(*) FROM watchlist').fetchone()[0] == 0


def test_tmdb_providers_br_groups_cache_and_official_links():
    from unittest.mock import Mock
    from app.integrations import TMDBClient
    response = Mock(status_code=200)
    response.json.return_value = {'results': {'US': {'flatrate': [{'provider_id': 999, 'provider_name': 'Other'}]},
        'BR': {'link': 'https://www.themoviedb.org/movie/1/watch?locale=BR',
               **{kind: [{'provider_id': index, 'provider_name': kind, 'logo_path': '/logo.jpg'}]
                  for index, kind in enumerate(['flatrate', 'free', 'ads', 'rent', 'buy'])}}}}
    session = Mock(); session.get.return_value = response
    tmdb = TMDBClient('test', session=session)
    data = tmdb.watch_providers('movie', 1)
    assert data['region'] == 'BR' and len(data['groups']) == 5
    assert data['groups'][0]['providers'][0]['name'] == 'flatrate'
    assert data['groups'][0]['providers'][0]['logo'].startswith('https://image.tmdb.org/')
    assert tmdb.watch_providers('movie', 1) == data
    assert session.get.call_count == 1
    tmdb.watch_providers('tv', 1)
    assert session.get.call_args.args[0].endswith('/tv/1/watch/providers')


def test_providers_absent_malformed_and_errors(client, services):
    from unittest.mock import Mock, patch
    import pytest
    from app.integrations import TMDBClient, IntegrationError
    tmdb = TMDBClient('test')
    tmdb.get = Mock(return_value={'results': {}})
    assert tmdb.watch_providers('movie', 1) == {'region': 'BR', 'groups': [], 'link': ''}
    tmdb.get.return_value = {'results': {'BR': {'link': 'https://example.com/pretend', 'rent': 'invalid'}}}
    with pytest.raises(IntegrationError):
        tmdb.watch_providers('movie', 1)
    assert client.get('/api/title/demo:movie:1/providers').json['groups'] == []
    with patch.object(services['catalog'], 'watch_providers', side_effect=IntegrationError('timeout')):
        response = client.get('/api/title/demo:movie:1/providers')
    assert response.status_code == 503 and response.json['message']


def test_omdb_valid_cache_missing_key_unavailable_and_expiration():
    from unittest.mock import Mock
    from app.integrations import OMDbClient
    session = Mock(); response = Mock(status_code=200)
    response.json.return_value = {'Response': 'True', 'imdbRating': '8.7'}
    session.get.return_value = response
    omdb = OMDbClient('test', session=session)
    assert omdb.cached_rating('tt1234567') is None and session.get.call_count == 0
    assert omdb.rating('tt1234567') == 8.7
    assert omdb.cached_rating('tt1234567') == 8.7
    assert omdb.rating('tt1234567') == 8.7 and session.get.call_count == 1
    key = next(iter(omdb._cache)); omdb._cache[key] = (0, omdb._cache[key][1])
    assert omdb.cached_rating('tt1234567') is None
    assert OMDbClient('', session=session).rating('tt1234567') is None
    assert omdb.parsed_rating({'imdbRating': 'N/A'}) is None
    assert omdb.parsed_rating({'imdbRating': 'NaN'}) is None
    assert omdb.parsed_rating({'imdbRating': 12}) is None


def test_imdb_external_id_fallback_and_distinct_cached_card_rating(client, services):
    from unittest.mock import Mock, patch
    from app.integrations import OMDbClient
    item = film(100, ['space travel'], (878,)); item.source = 'tmdb'; item.rating = 7.2
    session = Mock(); session.get.return_value = Mock(status_code=200)
    session.get.return_value.json.return_value = {'imdbRating': '8.7'}
    services['omdb'] = OMDbClient('test', session=session)
    with patch.object(services['catalog'], 'get', return_value=item), \
         patch.object(services['catalog'], 'search', return_value=[]), \
         patch.object(services['catalog']._tmdb, 'external_ids', return_value={'imdb_id': 'tt1234567'}) as external:
        html = client.get('/title/tmdb:movie:100').text
        assert '8.7/10' in html and '7.2/10' in html
        assert 'via OMDb' in html and 'TMDB' in html
        client.get('/title/tmdb:movie:100')
        assert external.call_count == 1 and session.get.call_count == 1
    with patch.object(services['catalog'], 'search', return_value=[item]):
        assert 'IMDb 8.7/10' in client.get('/?q=space').text
        assert session.get.call_count == 1


def test_no_imdb_placeholder_without_valid_data(client):
    html = client.get('/title/demo:movie:1').text
    assert 'via OMDb' not in html


def test_removed_awards_experience_and_banner_structure(client, services):
    assert 'awards' not in services
    assert 'Oscar' not in client.get('/title/demo:movie:1').text
    html = client.get('/').text
    assert html.count('class="hero-slide ') >= 5
    assert html.count('data-hero-index=') >= 5
    assert 'data-hero-pause' in html and 'data-hero-next' in html
    assert 'data-src=' in html and 'aria-roledescription=' in html
