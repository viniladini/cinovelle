from unittest.mock import Mock

import pytest
import requests

from app.integrations import IntegrationError, OMDbClient, TMDBClient
from app.services.catalog import CatalogService


def session_with(data=None, status=200):
    session = Mock()
    response = Mock(status_code=status)
    response.json.return_value = data or {}
    session.get.return_value = response
    return session


def test_tmdb_auth_cache_search_and_optional_credentials():
    session = session_with({'results': [{'id': 1}]})
    client = TMDBClient('key', 'token', session)
    assert client.search('test') == [{'id': 1}]
    client.search('test')
    assert session.get.call_count == 1
    kwargs = session.get.call_args.kwargs
    assert kwargs['headers']['Authorization'] == 'Bearer token'
    assert 'api_key' not in kwargs['params']
    assert kwargs['params']['language'] == 'pt-BR'
    key_session = session_with()
    TMDBClient('only-key', session=key_session).search('test', 'en-US', 'movie')
    assert key_session.get.call_args.kwargs['params']['api_key'] == 'only-key'
    with pytest.raises(IntegrationError):
        TMDBClient().search('x')


@pytest.mark.parametrize('status,code', [(401,'credentials'),(403,'credentials'),(404,'not_found'),(429,'rate_limit'),(500,'provider'),(503,'provider')])
def test_http_errors(status, code):
    with pytest.raises(IntegrationError) as error:
        TMDBClient('key', session=session_with(status=status)).search('x')
    assert error.value.code == code


def test_timeout_invalid_json_and_shape():
    session = Mock()
    session.get.side_effect = requests.Timeout
    with pytest.raises(IntegrationError, match='timeout'):
        TMDBClient('key', session=session).search('x')
    session = session_with()
    session.get.return_value.json.side_effect = ValueError
    with pytest.raises(IntegrationError):
        TMDBClient('key', session=session).search('x')
    session = session_with()
    session.get.return_value.json.return_value = []
    with pytest.raises(IntegrationError, match='invalid_response'):
        TMDBClient('key', session=session).search('x')


def test_keywords_differ_between_movie_and_tv():
    client = TMDBClient('key', session=session_with({'keywords': [{'id':1}], 'results': [{'id':2}]}))
    assert client.keywords('movie', 1, 'pt-BR') == [{'id':1}]
    assert client.keywords('tv', 1, 'pt-BR') == [{'id':2}]


def test_omdb_rating_missing_and_failure():
    assert OMDbClient().rating('tt123') is None
    assert OMDbClient('key', session=session_with({'imdbRating':'8.4'})).rating('tt1234567') == 8.4
    assert OMDbClient('key', session=session_with({'imdbRating':'N/A'})).rating('tt123') is None
    assert OMDbClient('key', session=session_with({'Response':'False','Error':'not found'})).rating('tt123') is None


@pytest.mark.parametrize('data', [{'results':None}, {'results':{}}, {'results':[None]}, {'results':[{'id':'1'}]}])
def test_invalid_results(data):
    with pytest.raises(IntegrationError, match='invalid_response'):
        TMDBClient('key', session=session_with(data)).search('x')


@pytest.mark.parametrize('data', [
    {'id':1,'title':5}, {'id':1,'genres':{}}, {'id':1,'genres':[None]},
    {'id':1,'keywords':[]}, {'id':1,'keywords':{'keywords':{}}},
    {'id':1,'credits':{'cast':5}}, {'id':1,'external_ids':[]},
])
def test_invalid_details(services, data):
    catalog = services['catalog']
    with pytest.raises(IntegrationError, match='invalid_response'):
        catalog._convert(data, 'movie')


def test_cache_expiry_and_independent_copies():
    session = session_with({'results':[{'id':1}]})
    client = TMDBClient('key', session=session)
    rows = client.search('x')
    rows.append({'id':2})
    assert client.search('x') == [{'id':1}]
    key = next(iter(client._cache))
    client._cache[key] = (0, {'results':[{'id':99}]})
    assert client.search('x') == [{'id':1}]
    assert session.get.call_count == 2


def test_search_genre_names_and_people_filter(services):
    tmdb = Mock(configured=True)
    tmdb.genres.return_value = [{'id':18,'name':'Drama'}]
    tmdb.search.return_value = [{'id':7,'media_type':'person','name':'Actor'},
                               {'id':8,'media_type':'movie','title':'Film','genre_ids':[18]},
                               {'id':9,'media_type':'tv','name':'Series','genre_ids':[18]}]
    catalog = CatalogService(tmdb, services['titles'])
    items = catalog.search('x', 'en-US')
    assert len(items) == 2
    assert [i.genres[0].name for i in items] == ['Drama','Drama']
    assert {i.media_type for i in items} == {'movie','tv'}


def test_omdb_unavailable_invalid_id_and_invalid_key():
    session = session_with({'imdbRating':'N/A'})
    client = OMDbClient('key', session=session)
    assert client.rating('tt1234567') is None
    assert client.rating(123) is None
    assert client.rating('invalid') is None
    assert session.get.call_count == 1
    with pytest.raises(IntegrationError, match='credentials'):
        OMDbClient('key', session=session_with({'Response':'False','Error':'Invalid API key!'})).rating('tt1234567')


def test_all_tmdb_endpoint_paths():
    session = session_with({'results':[], 'genres':[], 'keywords':[]})
    client = TMDBClient('key', session=session)
    client.search('x', 'en-US', 'tv')
    client.details('movie', 7, 'en-US')
    client.related('tv', 7, 'en-US', 'similar')
    client.discover('tv', {18,878}, 'en-US')
    client.genres('movie', 'en-US')
    client.external_ids('tv', 7, 'en-US')
    paths = [call.args[0].replace(client.BASE, '') for call in session.get.call_args_list]
    assert paths == ['/search/tv','/movie/7','/tv/7/similar','/discover/tv','/genre/movie/list','/tv/7/external_ids']
    assert session.get.call_args_list[1].kwargs['params']['append_to_response'] == 'keywords,external_ids,credits'


def test_empty_real_search_respects_media_filter(services):
    tmdb = Mock(configured=True)
    tmdb.discover.side_effect = lambda kind, ids, lang: [{'id':1,'name':'Series'}] if kind == 'tv' else [{'id':2,'title':'Film'}]
    tmdb.genres.return_value = []
    catalog = CatalogService(tmdb, services['titles'])
    assert {item.media_type for item in catalog.search('', media_type='tv')} == {'tv'}
    assert {item.media_type for item in catalog.search('')} == {'movie','tv'}


def test_partial_candidates_and_total_provider_failure(services):
    tmdb = Mock(configured=True)
    tmdb.details.return_value = {'id':1,'title':'Seed','genres':[{'id':18,'name':'Drama'}]}
    catalog = CatalogService(tmdb, services['titles'])
    seed = catalog.get('tmdb:movie:1')
    tmdb.related.side_effect = IntegrationError('rate_limit')
    tmdb.discover.side_effect = IntegrationError('timeout')
    with pytest.raises(IntegrationError):
        catalog.candidates([seed], 'pt-BR')
    tmdb.discover.side_effect = [[{'id':2}], IntegrationError('timeout')]
    tmdb.details.return_value = {'id':2,'title':'Candidate'}
    candidates, _ = catalog.candidates([seed], 'pt-BR')
    assert len(candidates) == 1


def test_catalog_real_conversion_and_cross_discovery(services):
    tmdb = Mock(configured=True)
    tmdb.details.side_effect = lambda kind, value, lang: {
        'id': value, 'title': 'A' if kind == 'movie' else None, 'name': 'B',
        'genres': [{'id':878 if kind == 'movie' else 10765,'name':'Science fiction'}],
        'keywords': {'keywords' if kind == 'movie' else 'results': [{'id':7}]},
        'external_ids': {'imdb_id':'tt123'}, 'credits': {'cast':[{'name':'Actor'}]},
        'vote_average': 9, 'vote_count':0,
    }
    tmdb.related.return_value = [{'id':2}]
    tmdb.discover.return_value = [{'id':3}]
    catalog = CatalogService(tmdb, services['titles'])
    seed = catalog.get('tmdb:movie:1')
    assert seed.rating is None and seed.keywords == {'7'} and seed.cast == ['Actor']
    candidates, related = catalog.candidates([seed], 'en-US')
    assert {item.media_type for item in candidates} == {'movie','tv'}
    assert 'tmdb:movie:2' in related[seed.key]
    tv = next(i for i in candidates if i.media_type == 'tv')
    assert tv.genre_ids() == {878}
    assert tmdb.discover.call_count == 2
    catalog.get('tmdb:movie:1')
    assert sum(call.args[1] == 1 for call in tmdb.details.call_args_list) == 1


def test_real_fallback_to_persisted_and_malformed_id(services):
    tmdb = Mock(configured=True)
    tmdb.details.side_effect = IntegrationError('timeout')
    catalog = CatalogService(tmdb, services['titles'])
    with pytest.raises(IntegrationError):
        catalog.get('tmdb:movie:99')
    with pytest.raises(LookupError):
        catalog.get('../../invalid')
