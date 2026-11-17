from unittest.mock import patch

from app.integrations import IntegrationError
from app.models import Genre, Movie, TVSeries
from app.services.recommendation import RecommendationEngine


def title(value, genres=(18, 10749), keywords=('city','memory','cinema'), rating=None, series=False):
    cls = TVSeries if series else Movie
    return cls(value, str(value), genres=[Genre(g, str(g)) for g in genres], keywords=set(keywords), rating=rating)


def recommend(seeds, candidates, related=None, **filters):
    return RecommendationEngine(evidence_aware=True).recommend(seeds, candidates, related, **filters)


def test_strong_content_affinity_without_optional_providers():
    a, b = title(1), title(2)
    result = recommend([a], [b])[0]
    assert result.score == 100
    assert result.factors['reliability'] == 1
    assert result.factors['related_available'] == 0
    assert result.factors['rating_available'] == 0


def test_extra_genres_not_excessively_penalized():
    a, b = title(1), title(2, genres=(18, 10749, 35))
    current = recommend([a], [b])[0]
    classic = RecommendationEngine().recommend([a], [b])[0]
    assert current.factors['genre'] == (2 / 3 + 1) / 2
    assert current.score > classic.score
    assert current.score < 100


def test_sparse_evidence_and_rating_cannot_create_high_affinity():
    a = title(1, genres=(18,), keywords=())
    b = title(2, genres=(18,), keywords=(), rating=10)
    assert recommend([a], [b])[0].score <= 50
    unrelated = title(3, genres=(35,), keywords=(), rating=10)
    assert recommend([a], [unrelated])[0].score == 10
    one_keyword = title(4, genres=(18,), keywords=('generic',))
    other = title(5, genres=(18,), keywords=('generic',))
    result = recommend([one_keyword], [other])[0]
    assert result.score < 70 and result.factors['reliability'] < 1
    genres_only = title(8, genres=(18,35,12), keywords=())
    similar = title(9, genres=(18,35,12), keywords=())
    assert recommend([genres_only], [similar])[0].score == 40
    no_data = title(6, genres=(), keywords=())
    assert recommend([no_data], [no_data, title(7, genres=(), keywords=())])[0].score == 0


def test_missing_relation_is_different_from_observed_non_relation():
    a, b = title(1), title(2)
    unavailable = recommend([a], [b], {})[0]
    absent = recommend([a], [b], {a.key: set()})[0]
    positive = recommend([a], [b], {a.key: {b.key}})[0]
    assert absent.score < unavailable.score == positive.score
    assert absent.factors['related_available'] == 1


def test_weighted_keywords_distinguish_rare_and_common_evidence():
    a = title(1, keywords=('rare','common'))
    rare = title(2, keywords=('rare',))
    common = title(3, keywords=('common',))
    background = [title(i, keywords=('common',)) for i in range(4, 10)]
    results = {r.item.key: r for r in recommend([a], [rare, common, *background])}
    assert results[rare.key].factors['keyword'] > results[common.key].factors['keyword']


def test_multi_profile_recurrence_order_dedup_and_filters():
    a = title(1, genres=(18,10749), keywords=('shared','a','b'))
    b = title(2, genres=(18,35), keywords=('shared','c','d'))
    shared = title(3, genres=(18,), keywords=('shared',), series=True)
    unique = title(4, genres=(10749,), keywords=('a',), series=True)
    results = recommend([a,b], [a,b,shared,unique,shared], media_type='tv', genre_id=None)
    assert len(results) == 2
    assert results[0].item.key == shared.key
    assert [(r.item.key,r.score) for r in results] == [(r.item.key,r.score) for r in recommend([b,a], [unique,shared], media_type='tv')]
    assert all(r.item.key == shared.key for r in recommend([a,b], [shared,unique], preferences=[18]))
    assert recommend([a,b], [shared,unique], genre_id=878) == []


def test_missing_seed_data_reduces_confidence_in_multi_selection():
    a, b, candidate = title(1), title(2, genres=(), keywords=()), title(3)
    assert recommend([a,b], [candidate])[0].score < recommend([a], [candidate])[0].score


def test_cross_media_relations_are_unavailable_not_negative():
    a, b = title(1), title(2, series=True)
    result = recommend([a], [b], {a.key:set()})[0]
    assert result.factors['related_available'] == 0 and result.score == 100


def test_dynamic_search_and_selection_without_navigation(client, post):
    assert client.get('/api/search?q=o').json == {'items':[]}
    data = client.get('/api/search?q=orbita').json
    assert len(data['items']) == 1
    item = data['items'][0]
    assert item['media_type'] == 'tv' and item['poster'] and item['year']
    response = post('/selection', {'key':item['key']}, headers={'Accept':'application/json'})
    assert response.status_code == 200 and response.json['selected'][0]['key'] == item['key']
    assert client.get('/api/search?q=orbita').json['items'][0]['selected'] is True
    response = post('/selection', {'key':item['key'],'action':'remove'}, headers={'Accept':'application/json'})
    assert response.json['selected'] == []
    assert client.get('/api/search?q=zzzzzz').json['items'] == []


def test_dynamic_selection_maximum_and_csrf(client, post):
    headers = {'Accept':'application/json'}
    keys = ['demo:movie:1','demo:movie:2','demo:tv:3','demo:movie:4','demo:tv:5']
    for key in keys:
        assert post('/selection', {'key':key}, headers=headers).status_code == 200
    response = post('/selection', {'key':'demo:movie:6'}, headers=headers)
    assert response.status_code == 400 and response.json['message']
    assert len(post('/selection', {'key':keys[0]}, headers=headers).json['selected']) == 5
    assert client.post('/selection', data={'key':keys[0]}, headers=headers).status_code == 400


def test_async_favorites_sqlite_idempotence_and_cards(client, post, services):
    headers = {'Accept':'application/json'}
    response = post('/favorites', {'key':'demo:movie:1'}, headers=headers)
    assert response.status_code == 401 and response.json['message']
    post('/profiles', {'name':'Interface'})
    for _ in range(2):
        result = post('/favorites', {'key':'demo:movie:1'}, headers=headers)
        assert result.status_code == 200 and result.json['favorite'] is True
    assert len(services['favorites'].list(1)) == 1
    assert client.get('/api/search?q=sessao').json['items'][0]['favorite'] is True
    html = client.get('/').text
    assert 'data-favorite' in html and 'aria-pressed="true"' in html
    post('/selection', {'key':'demo:movie:9'}, headers=headers)
    assert 'data-favorite' in post('/recommendations').text
    response = post('/favorites', {'key':'demo:movie:1','action':'remove'}, headers=headers)
    assert response.json['favorite'] is False and services['favorites'].list(1) == []
    assert client.get('/api/search?q=sessao').json['items'][0]['favorite'] is False


def test_suggestions_tmdb_mock_errors_and_language(client, post, services):
    item = title(99, series=True)
    item.source = 'tmdb'
    with patch.object(services['catalog'], 'search', return_value=[item]) as search:
        assert client.get('/api/search?q=real').json['items'][0]['key'] == item.key
        search.assert_called_once_with('real','pt-BR','both')
    with patch.object(services['catalog'], 'search', side_effect=IntegrationError('rate_limit')):
        response = client.get('/api/search?q=real')
        assert response.status_code == 503 and 'message' in response.json
    post('/language/en-US')
    assert client.get('/api/search?q=orbit').json['items'][0]['media_label'] == 'Series'
    assert client.get('/api/search?q=xx&type=invalid').status_code == 400


def test_home_markup_accessibility_and_no_page_reload_fallback(client):
    html = client.get('/').text
    assert html.index('id="title-query"') < html.index('id="selection-tray"') < html.index('id="recommend-button"')
    assert 'aria-controls="suggestions"' in html
    assert 'role="dialog"' in html and 'id="search-skeleton"' in html
    assert 'id="recommend-shortcut"' in html
    assert client.get('/static/interaction-utils.js').status_code == 200
