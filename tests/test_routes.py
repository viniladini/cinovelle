def test_pages_and_demo(client):
    home = client.get('/')
    assert home.status_code == 200
    assert 'obras fictícias' in home.text
    assert 'Depois da última sessão' in home.text
    assert client.get('/?q=orbita').status_code == 200
    assert 'Órbita distante' in client.get('/?q=orbita').text
    assert 'Depois da última sessão' not in client.get('/?q=orbita').text
    assert client.get('/title/demo:movie:1').status_code == 200
    assert client.get('/title/demo:movie:999').status_code == 404
    assert client.get('/missing').status_code == 404
    assert client.get('/favorites').status_code == 302
    assert client.get('/taste').status_code == 302


def test_complete_profile_selection_recommendation_favorites_history_flow(client, post, services):
    assert post('/profiles', {'name':'Marina'}, follow_redirects=True).status_code == 200
    assert post('/taste', {'name':'Lia','genres':['18']}).status_code == 302
    assert services['profiles'].all()[0].preferences == [18]
    for key in ['demo:movie:1', 'demo:movie:4']:
        assert post('/selection', {'key':key}, follow_redirects=True).status_code == 200
    result = post('/recommendations', {'type':'tv','genre':'18'}, follow_redirects=True)
    assert result.status_code == 200 and 'de afinidade' in result.text
    runs = services['history'].list(1)
    assert len(runs) == 1 and all(r['item'].media_type == 'tv' for r in runs[0]['results'])
    assert client.get('/taste').status_code == 200
    assert post('/favorites', {'key':'demo:movie:1'}, follow_redirects=True).status_code == 200
    assert 'Depois da última sessão' in client.get('/favorites').text
    assert post('/favorites', {'key':'demo:movie:1','action':'remove','return_to':'favorites'}, follow_redirects=True).status_code == 200
    assert services['favorites'].list(1) == []
    post('/history/delete', {'run_id':str(runs[0]['id'])})
    assert services['history'].list(1) == []
    assert post('/logout', follow_redirects=True).status_code == 200
    assert post('/profiles/1/enter').status_code == 302
    assert post('/profiles/1/delete', follow_redirects=True).status_code == 200
    assert services['profiles'].all() == []


def test_selection_limits_removal_filters_and_errors(client, post):
    assert post('/recommendations').status_code == 400
    assert post('/profiles', {'name':' '}).status_code == 400
    keys = ['demo:movie:1','demo:movie:2','demo:tv:3','demo:movie:4','demo:tv:5']
    for key in keys:
        assert post('/selection', {'key':key}).status_code == 302
    assert post('/selection', {'key':'demo:movie:6'}).status_code == 400
    post('/selection', {'key':keys[0],'action':'remove'})
    with client.session_transaction() as session:
        assert keys[0] not in session['selection']
    assert post('/recommendations', {'type':'bad'}).status_code == 400
    assert post('/recommendations', {'genre':'bad'}).status_code == 400
    assert client.get('/?type=bad').status_code == 400


def test_csrf_language_persistence_and_safe_forms(client, post):
    assert client.post('/profiles', data={'name':'X'}).status_code == 400
    assert post('/language/en-US', follow_redirects=True).status_code == 200
    assert 'Your next story starts here.' in client.get('/').text
    assert 'After the Last Screening' in client.get('/').text
    assert post('/language/xx').status_code == 404
    assert post('/profiles', {'name':'<script>alert(1)</script>'}, follow_redirects=True).status_code == 200
    assert '<script>alert(1)</script>' not in client.get('/profiles').text


def test_error_pages_and_preferences_validation(client, post, services):
    from app.integrations import IntegrationError
    from unittest.mock import patch
    post('/profiles', {'name':'Test'})
    assert post('/taste', {'name':'Test','genres':['999999']}).status_code == 400
    assert post('/taste', {'name':'Test','genres':['invalid']}).status_code == 400
    with patch.object(services['catalog'], 'search', side_effect=IntegrationError('rate_limit')):
        response = client.get('/')
        assert response.status_code == 200
        assert 'Limite de consultas' in response.text
    with patch.object(services['catalog'], 'get', side_effect=IntegrationError('credentials')):
        assert client.get('/title/tmdb:movie:7').status_code == 503
    assert client.get('/logout').status_code == 405
    assert post('/profiles/999/enter').status_code == 404


def test_genre_preference_filter_and_profile_isolation(client, post, services):
    post('/profiles', {'name':'A'})
    post('/taste', {'name':'A','genres':['878']})
    post('/selection', {'key':'demo:movie:1'})
    result = post('/recommendations', {'preferences':'on'})
    assert result.status_code == 200
    assert all(878 in entry['item'].genre_ids() for entry in services['history'].list(1)[0]['results'])
    post('/favorites', {'key':'demo:movie:1'})
    post('/profiles', {'name':'B'})
    assert services['favorites'].list(2) == []
    run_id = services['history'].list(1)[0]['id']
    post('/history/delete', {'run_id':str(run_id)})
    assert services['history'].list(1)
    post('/profiles/1/enter')
    with client.session_transaction() as session:
        assert 'selection' not in session


def test_all_local_assets_exist(client):
    for index in range(1,19):
        response = client.get(f'/static/posters/{index}.svg')
        assert response.status_code == 200 and '<svg' in response.text
    for name in ['style.css','app.js','tmdb.svg']:
        assert client.get(f'/static/{name}').status_code == 200
