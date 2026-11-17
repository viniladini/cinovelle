import json
import re
from unittest.mock import patch

from app.models import Movie, TVSeries


def config(response):
    return json.loads(re.search(r'id="interaction-config" type="application/json">(.*?)</script>',
                                response.text, re.S)[1])


def test_selection_survives_internal_pages_and_remains_independent_from_favorites(client, post):
    post('/profiles', {'name': 'Discovery'})
    post('/selection', {'key': 'demo:movie:1'})
    post('/favorites', {'key': 'demo:movie:2'})
    for path in ['/explore', '/title/demo:movie:1', '/favorites', '/taste', '/profiles']:
        response = client.get(path)
        assert response.status_code == 200
        state = config(response)
        assert state['selected'] == ['demo:movie:1']
        assert state['favorites'] == ['demo:movie:2']
        assert 'id="selection-tray"' in response.text
        assert 'id="title-query"' in response.text
        assert 'id="recommend-shortcut"' in response.text


def test_explore_filters_media_and_genres_and_preserves_query(client):
    response = client.get('/explore?q=orbita&type=tv&genre=878')
    assert response.status_code == 200
    assert 'demo:tv:3' in response.text
    assert 'demo:movie:1' not in response.text
    assert 'value="orbita"' in response.text
    assert client.get('/explore?genre=invalid').status_code == 400
    assert client.get('/explore?type=invalid').status_code == 400


def test_featured_uses_available_movie_backdrop_without_fixed_title(client, services):
    series = TVSeries(991, 'Series example', backdrop='https://image.tmdb.org/t/p/w1280/series.jpg')
    movie = Movie(992, 'Feature example', backdrop='https://image.tmdb.org/t/p/w1280/feature.jpg', rating=8.1)
    with patch.object(services['catalog'], 'search', return_value=[series, movie]):
        response = client.get('/')
    assert response.status_code == 200
    assert '<h1>Feature example</h1>' in response.text
    assert 'class="hero-backdrop"' in response.text
    assert 'TMDB 8.1/10' in response.text


def test_find_similar_uses_engine_and_preserves_current_selection(client, post, services):
    post('/profiles', {'name': 'Similar'})
    post('/selection', {'key': 'demo:movie:2'})
    seed = services['catalog'].get('demo:movie:1')
    candidates, related = services['catalog'].candidates([seed], 'pt-BR')
    expected = services['engine'].recommend([seed], candidates, related)
    response = post('/similar/demo:movie:1')
    assert response.status_code == 200
    assert config(response)['selected'] == ['demo:movie:2']
    assert response.text.count('id="discovery"') == 1
    assert response.text.count('id="selection-tray"') == 1
    assert response.text.count('id="recommend-form"') == 1
    assert response.text.count('id="recommend-shortcut"') == 1
    history = services['history'].list(1)
    assert len(history) == 1 and history[0]['seeds'][0]['key'] == seed.key
    assert [(row['item'].key, row['score']) for row in history[0]['results']] == [
        (result.item.key, result.score) for result in expected if result.score >= 70]
    assert 'id="result-type"' in response.text and 'id="result-genre"' in response.text
    if any(result.score >= 70 for result in expected):
        assert 'data-type="' in response.text and 'data-genres="' in response.text
        assert 'class="reason"' in response.text
    else:
        assert 'Não encontramos matches' in response.text
        assert 'class="media-card"' not in response.text
    assert client.get('/similar/demo:movie:1').status_code == 405
    assert client.post('/similar/demo:movie:1').status_code == 400


def test_home_preferences_rail_and_english_copy(client, post):
    post('/profiles', {'name': 'Taste'})
    post('/taste', {'name': 'Taste', 'genres': ['878']})
    assert 'id="personal-rail"' in client.get('/').text
    post('/language/en-US')
    html = client.get('/').text
    assert 'Find my matches' in html and 'In the spotlight' in html
    assert 'Featured series' in html
    assert 'class="hero-demo-poster"' in html
    hero = re.search(r'<section class="cinema-hero.*?</section>', html, re.S)[0]
    assert 'TMDB ' not in hero
