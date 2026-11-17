from unittest.mock import Mock

from app.integrations import TMDBClient
from app.services.catalog import CatalogService


def test_missing_append_fetches_keywords_without_inventing_values():
    client = TMDBClient('test')
    client.get = Mock(side_effect=[{'id':1,'title':'Film'}, {'keywords':[{'id':7}]}])
    data = client.details('movie',1,'pt-BR')
    assert data['keywords'] == {'keywords':[{'id':7}]}
    assert client.get.call_args.args[0] == '/movie/1/keywords'


def test_valid_empty_keywords_are_not_requeried():
    client = TMDBClient('test')
    client.get = Mock(return_value={'id':1,'keywords':{'keywords':[]}})
    client.details('movie',1,'pt-BR')
    assert client.get.call_count == 1


def test_candidate_type_filter_is_applied_before_hydration(services):
    tmdb = Mock(configured=True)
    tmdb.details.side_effect = lambda kind, value, lang: {'id':value, 'title':'Item'}
    tmdb.related.return_value = [{'id':i} for i in range(1,20)]
    tmdb.discover.return_value = [{'id':i} for i in range(20,32)]
    catalog = CatalogService(tmdb, services['titles'])
    seed = catalog.get('tmdb:movie:1')
    candidates, related = catalog.candidates([seed], 'pt-BR', 'tv',18)
    assert candidates and all(item.media_type == 'tv' for item in candidates)
    assert all(call.args[0] == 'tv' for call in tmdb.discover.call_args_list)
    assert all(call.args[0] == 'tv' for call in tmdb.details.call_args_list[1:])
    assert seed.key not in {item.key for item in candidates}
    assert 'tmdb:movie:19' in related[seed.key]
