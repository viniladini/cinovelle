import re
from unittest.mock import Mock, patch

import pytest

from app.integrations import IntegrationError, TMDBClient
from app.models import Genre, Movie, Recommendation, TVSeries
from app.services.catalog import CatalogService
from app.services.match import MatchScorer, RelationEvidence, tokens
from app.services.recommendation import RecommendationEngine


def title(value, *, keywords=('space', 'time', 'planet', 'mission'), genres=(878, 18), overview='', tv=False, rating=None):
    cls = TVSeries if tv else Movie
    return cls(value, f'Title {value}', genres=[Genre(g, str(g)) for g in genres],
               keywords=set(keywords), overview=overview, rating=rating)


def rank(seeds, candidates, related=None, **filters):
    return RecommendationEngine(version=2).recommend(seeds, candidates, related, **filters)


def test_strong_match_requires_actual_multidimensional_evidence():
    seed = title(1)
    match = title(2, genres=(878, 18, 12))
    mismatch = title(3, keywords=('family', 'marriage', 'wedding', 'divorce'))
    popular = title(4, keywords=('battle', 'war'), genres=(10752,), rating=10)
    results = {row.item.key: row for row in rank([seed], [match, mismatch, popular])}
    assert 80 <= results[match.key].score < 100
    assert results[mismatch.key].score < 70
    assert results[popular.key].score < 70
    assert results[match.key].factors['algorithm_version'] == 2
    assert 'reason_themes' in results[match.key].explanation_keys
    assert 'reason_themes' not in results[mismatch.key].explanation_keys


@pytest.mark.parametrize('candidate', [title(2, keywords=()), title(2, genres=()),
                                     title(2, genres=(), keywords=(), rating=10),
                                     title(2, keywords=('space',))])
def test_sparse_metadata_never_reaches_eighty(candidate):
    result = rank([title(1)], [candidate])[0]
    assert result.score < 80
    assert result.factors['reliability'] < 1


def test_missing_optional_data_is_not_negative_evidence_and_cross_media_works():
    seed, same = title(1), title(2, tv=True)
    result = rank([seed], [same], {seed.key: set()})[0]
    assert result.score >= 90
    assert result.factors['related_available'] == 0
    assert result.factors['overview_available'] == 0
    assert rank([seed], [title(3)], {seed.key: set()})[0].score == result.score
    assert result.factors['shared_keywords'] == 4


def test_synopsis_tfidf_supports_missing_keywords_without_inventing_themes():
    story = 'Astronaut scientists travel through wormhole searching distant planets rescue humanity earth mission'
    seed = title(1, keywords=(), overview=story)
    similar = title(2, keywords=(), overview=story + ' galaxy')
    unrelated = title(3, keywords=(), overview='Brothers inherit family bakery and prepare wedding dinner for neighbors')
    results = {row.item.key: row for row in rank([seed], [similar, unrelated])}
    assert results[similar.key].score >= 80
    assert results[unrelated.key].score < 70
    assert 'reason_narrative' in results[similar.key].explanation_keys
    assert 'reason_themes' not in results[similar.key].explanation_keys
    assert 'reason_narrative' not in results[unrelated.key].explanation_keys
    assert tokens('Uma missão no espaço com uma família.') == {'missao': 1, 'espaco': 1, 'familia': 1}


def test_keywords_and_synopses_that_disagree_are_not_erased():
    story = 'An astronaut travels distant planets cosmic wormhole science mission galaxy'
    seed = title(1, overview=story)
    identical = title(2, overview=story)
    different = title(3, overview='A bakery hosts wedding celebrations families marry brothers divorce neighbors')
    rows = {row.item.key: row for row in rank([seed], [identical, different])}
    assert rows[identical.key].score > rows[different.key].score
    assert rows[different.key].factors['overview_available'] == 1
    assert rows[different.key].factors['overview'] == 0


def test_keyword_names_are_preserved_and_word_variants_are_compared(services):
    tmdb = Mock(configured=True)
    tmdb.details.return_value = {'id': 1, 'title': 'Reference', 'keywords': {
        'keywords': [{'id': 7, 'name': 'racism'}, {'id': 8, 'name': 'space travel'}]}}
    seed = CatalogService(tmdb, services['titles']).get('tmdb:movie:1')
    assert seed.keywords == {'7', '8'}
    assert seed.keyword_names == {'7': 'racism', '8': 'space travel'}
    saved = services['titles'].get('tmdb', 'movie', 1)
    assert saved.keyword_names == seed.keyword_names
    a, b = title(101), title(102)
    a.keyword_names = {'space': 'space travel', 'time': 'racism', 'planet': 'planet', 'mission': 'mission'}
    b.keyword_names = {'space': 'space travelling', 'time': 'racist', 'planet': 'planet', 'mission': 'mission'}
    result = rank([a], [b])[0]
    assert result.factors['shared_themes'] >= 3
    assert result.score >= 80


def test_one_verbose_tag_does_not_create_multiple_independent_themes():
    a, b = title(1, keywords=('one',)), title(2, keywords=('one',))
    a.keyword_names = b.keyword_names = {'one': 'father daughter family relationship'}
    result = rank([a], [b])[0]
    assert result.factors['shared_themes'] >= 3
    assert result.factors['thematic_tags'] == 1
    assert result.score < 80


def test_distinct_interests_are_not_diluted_and_results_are_diversified():
    space = title(1)
    horror = title(2, keywords=('haunted', 'ghost', 'curse', 'ritual'), genres=(27, 53))
    candidates = [title(value) for value in range(10, 14)] + [
        title(20, keywords=horror.keywords, genres=(27, 53)), title(21, keywords=horror.keywords, genres=(27, 53))]
    results = rank([space, horror], candidates)
    assert all(row.score >= 80 for row in results)
    assert len({row.factors['group_id'] for row in results[:2]}) == 2
    assert len(MatchScorer([space, horror], candidates, {}).groups) == 2
    assert [(row.item.key, row.score) for row in results] == [
        (row.item.key, row.score) for row in rank([horror, space], list(reversed(candidates)))]


def test_recurrent_profile_shared_themes_and_relations_are_explained_truthfully():
    a, b, c = title(1), title(2, keywords=('space', 'time', 'planet', 'astronaut')), title(3)
    related = {a.key: {c.key}, b.key: {c.key}}
    result = rank([a, b], [c], related)[0]
    assert result.score >= 80
    assert result.factors['group_size'] == 2
    assert result.factors['related_count'] == 2
    assert 'reason_relations' in result.explanation_keys
    assert rank([a], [c], {})[0].factors['related_available'] == 0


def test_no_relative_normalization_deduplication_exclusion_and_filters():
    seed = title(1)
    poor = title(2, keywords=('wedding', 'marriage'), genres=(10749,))
    assert rank([seed], [poor])[0].score < 70
    assert rank([seed], [seed, poor, poor], media_type='tv') == []
    a, b = title(3), title(3, tv=True)
    results = rank([seed], [seed, a, a, b])
    assert {row.item.key for row in results} == {a.key, b.key}
    assert all(row.item.key != seed.key for row in results)
    assert rank([seed], [a, b], genre_id=27) == []
    assert rank([seed], [a, b], preferences=[27]) == []


def test_insufficient_strong_matches_expand_once_and_preserve_partial_results():
    seed = title(1)
    partial = title(2, keywords=())
    strong = title(3)
    catalog = Mock(demo=False)
    catalog.candidates.side_effect = [([partial], {}), ([partial, strong], {})]
    results = RecommendationEngine(version=2).discover(catalog, [seed], 'pt-BR')
    assert results[0].item.key == strong.key
    assert catalog.candidates.call_count == 2
    assert catalog.candidates.call_args.kwargs == {'expanded': True}
    catalog.candidates.side_effect = [([strong], {}), IntegrationError('timeout')]
    assert RecommendationEngine(version=2).discover(catalog, [seed], 'pt-BR')[0].item.key == strong.key
    catalog.candidates.side_effect = None
    catalog.candidates.return_value = ([title(3, genres=(35,), keywords=())], {})
    assert not [row for row in RecommendationEngine(version=2).discover(catalog, [seed], 'pt-BR') if row.score >= 70]


def test_sufficient_strong_matches_and_demo_do_not_expand():
    catalog = Mock(demo=False)
    catalog.candidates.return_value = ([title(value) for value in range(2, 8)], {})
    assert len(RecommendationEngine(version=2).discover(catalog, [title(1)], 'pt-BR')) == 6
    assert catalog.candidates.call_count == 1
    catalog.demo = True
    catalog.candidates.reset_mock()
    RecommendationEngine(version=2).discover(catalog, [title(1)], 'pt-BR')
    assert catalog.candidates.call_count == 1


def test_discovery_keyword_combinations_and_page_are_sent_to_tmdb():
    client = TMDBClient('test')
    client.get = Mock(return_value={'results': []})
    client.discover('tv', {18, 10765}, 'en-US', keyword_ids={7, 9}, match_all=True, page=2)
    assert client.get.call_args.args == ('/discover/tv', 'en-US')
    assert client.get.call_args.kwargs['with_genres'] == '18,10765'
    assert client.get.call_args.kwargs['with_keywords'] == '7,9'
    assert client.get.call_args.kwargs['page'] == 2


def test_retrieval_hydration_budget_cache_keyword_expansion_and_cross_type(services):
    tmdb = Mock(configured=True)
    tmdb.related.return_value = [{'id': value, 'genre_ids': [878, 18]} for value in range(2, 202)]
    tmdb.discover.return_value = [{'id': value, 'genre_ids': [878, 18]} for value in range(150, 350)]
    tmdb.details.side_effect = lambda kind, value, language: {
        'id': value, 'title': f'Film {value}', 'genres': [{'id': 878, 'name': 'Sci-fi'}],
        'keywords': {'keywords' if kind == 'movie' else 'results': [{'id': value} for value in range(1, 5)]}}
    catalog = CatalogService(tmdb, services['titles'])
    seed = catalog.get('tmdb:movie:1')
    items, _ = catalog.candidates([seed], 'pt-BR')
    assert len(items) == 32
    assert {item.media_type for item in items} == {'movie', 'tv'}
    assert any(call.kwargs.get('keyword_ids') for call in tmdb.discover.call_args_list)
    expanded, _ = catalog.candidates([seed], 'pt-BR', expanded=True)
    assert len(expanded) == 64
    assert {item.key for item in items} <= {item.key for item in expanded}
    assert tmdb.details.call_count == 65
    assert tmdb.related.call_count + tmdb.discover.call_count <= 22
    assert any(call.kwargs.get('match_all') for call in tmdb.discover.call_args_list)
    before = tmdb.details.call_count, tmdb.discover.call_count
    catalog.candidates([seed], 'pt-BR', expanded=True)
    assert (tmdb.details.call_count, tmdb.discover.call_count) == before


def test_promising_source_position_precedes_arbitrary_external_id(services):
    tmdb = Mock(configured=True)
    tmdb.related.return_value = [{'id': value, 'genre_ids': [878, 18]}
                                for value in [999999, *range(2, 102)]]
    tmdb.discover.return_value = []
    tmdb.details.side_effect = lambda kind, value, language: {'id': value, 'title': str(value)}
    catalog = CatalogService(tmdb, services['titles'])
    seed = title(1, keywords=())
    seed.source = 'tmdb'
    items, _ = catalog.candidates([seed], 'pt-BR', 'movie')
    assert len(items) == 32
    assert items[0].external_id == 999999


def test_low_affinity_candidates_do_not_reappear_in_new_history(client, post, services):
    post('/profiles', {'name': 'Match'})
    post('/selection', {'key': 'demo:movie:1'})
    rows = [Recommendation(title(value), score, {'algorithm_version': 2}, [])
            for value, score in [(101, 90), (102, 79), (103, 69)]]
    with patch.object(services['engine'], 'discover', return_value=rows):
        post('/recommendations')
    history = services['history'].list(1)[0]['results']
    assert [row['score'] for row in history] == [90, 79]


@pytest.mark.parametrize('score,tier', [(100,'exceptional'), (90,'exceptional'), (89,'very_high'),
                                       (80,'very_high'), (79,'good'), (70,'good'), (69,'limited')])
def test_classification_boundaries(score, tier):
    assert Recommendation(title(1), score, {}, []).tier == tier


def test_single_results_section_filters_evidence_instead_of_score_threshold(client, post, services):
    post('/selection', {'key': 'demo:movie:1'})
    rows = [Recommendation(title(value), score, {'algorithm_version': 2}, [])
            for value, score in [(101, 90), (102, 80), (103, 79), (104, 70), (105, 69)]]
    with patch.object(services['engine'], 'discover', return_value=rows):
        response = post('/recommendations')
    assert 'id="match-results"' in response.text
    assert all(f'Title {value}' in response.text for value in range(101,105))
    assert 'Title 105' not in response.text
    assert 'id="strong-results"' not in response.text and 'id="alternative-results"' not in response.text
    with patch.object(services['engine'], 'discover', return_value=[]):
        response = post('/recommendations')
    assert 'Não encontramos candidatos' in response.text
    assert 'id="alternative-results"' not in response.text
    assert 'class="media-card"' not in response.text


def test_calibration_accumulates_shared_facts_without_dilution_by_incidental_tags():
    a = title(1, keywords=tuple(f'theme-{value}' for value in range(20)))
    b = title(2, keywords=('theme-0', 'theme-1', 'theme-2', 'theme-3', 'theme-4'))
    weak = title(3, keywords=('theme-0',))
    unrelated = title(4, keywords=('wedding', 'marriage', 'romance'), genres=(35, 10749), rating=10)
    results = {row.item.key: row for row in rank([a], [b, weak, unrelated], {a.key: {b.key, weak.key}})}
    assert results[b.key].score >= 80
    assert results[b.key].factors['thematic_units'] == 5
    assert results[weak.key].score < 80
    assert results[unrelated.key].score < 70
    assert not results[unrelated.key].is_relevant


def test_exceptional_requires_multiple_strong_signals_and_not_just_a_relation():
    story = 'Scientists astronauts explore distant planets wormhole rescue humanity cosmic mission'
    seed, match = title(1, overview=story), title(2, overview=story, rating=8)
    row = rank([seed], [match], {seed.key: {match.key}})[0]
    assert row.score >= 90
    conflicting = title(3, keywords=('wedding', 'family', 'school', 'marriage'),
                        overview='Families celebrate wedding festivities marriage guests dancing village hotel', rating=10)
    row = rank([seed], [conflicting], {seed.key: {conflicting.key}})[0]
    assert row.score < 70
    assert not row.is_relevant


def test_shared_production_metadata_does_not_count_as_thematic_affinity():
    names = dict(enumerate(['woman director', 'independent film', 'based on novel or book', 'remake']))
    a, b = title(1, keywords=tuple(map(str, names))), title(2, keywords=tuple(map(str, names)))
    a.keyword_names = b.keyword_names = {str(key): value for key, value in names.items()}
    row = rank([a], [b], {a.key: {b.key}})[0]
    assert row.factors['thematic_units'] == 0
    assert row.factors['keyword'] == 0
    assert row.score < 70


def test_relation_provenance_distinguishes_recommendations_from_broad_similars():
    seed, candidate = title(1), title(2)
    values = {seed.key: {candidate.key}}
    recommended = RelationEvidence(values, sources={seed.key: {'recommendations': {candidate.key}}})
    similar = RelationEvidence(values, sources={seed.key: {'similar': {candidate.key}}})
    a, b = rank([seed], [candidate], recommended)[0], rank([seed], [candidate], similar)[0]
    assert a.factors['related'] == 1
    assert b.factors['related'] == .5
    assert a.score > b.score
    assert recommended.strength(seed.key, candidate.key) == 1


def test_points_explain_scores_including_caps_and_rounding():
    seed = title(1)
    candidates = [title(2, rating=8), title(3, keywords=('space',), rating=7), title(4, keywords=())]
    for row in rank([seed], candidates, {seed.key: {item.key for item in candidates}}):
        f = row.factors
        points = sum(f[f'{key}_points'] for key in ('keyword', 'genre', 'related', 'overview', 'rating'))
        assert points - f['evidence_cap_points'] + f['rounding_points'] == pytest.approx(row.score)
        assert 0 <= f['rating_points'] <= 2
        assert 0 <= f['overview_points'] <= 8
        assert 0 <= f['reliability'] <= 1


def test_missing_text_does_not_outscore_rich_matching_metadata():
    story = 'Astronaut scientists explore planets wormhole cosmic rescue humanity mission'
    seed = title(1, overview=story)
    rich, sparse = title(2, overview=story), title(3, keywords=(), overview='')
    rows = {row.item.key: row for row in rank([seed], [rich, sparse], {seed.key: {rich.key, sparse.key}})}
    assert rows[rich.key].score >= 90
    assert rows[sparse.key].score < 70
    assert rows[sparse.key].is_relevant


def test_five_good_alternatives_do_not_trigger_unnecessary_expansion():
    seed = title(1)
    catalog = Mock(demo=False)
    catalog.candidates.return_value = ([], {})
    rows = [Recommendation(title(value), 75, {'group_id': 0, 'group_size': 1, 'relevant_evidence': 1}, [])
            for value in range(2, 7)]
    engine = RecommendationEngine(version=2)
    with patch.object(engine, 'recommend', return_value=rows):
        assert engine.discover(catalog, [seed], 'pt-BR') == rows
    assert catalog.candidates.call_count == 1


def test_retrieval_without_attributes_does_not_fall_back_to_random_popularity(services):
    tmdb = Mock(configured=True)
    tmdb.related.return_value = []
    seed = title(1, genres=(), keywords=())
    seed.source = 'tmdb'
    items, _ = CatalogService(tmdb, services['titles']).candidates([seed], 'pt-BR')
    assert items == []
    tmdb.discover.assert_not_called()


def test_relation_sources_survive_cache_and_expansion(services):
    tmdb = Mock(configured=True)
    tmdb.related.side_effect = lambda kind, value, language, endpoint: [{'id': 2 if endpoint == 'recommendations' else 3}]
    tmdb.discover.return_value = []
    tmdb.details.side_effect = lambda kind, value, language: {'id': value, 'title': str(value)}
    catalog = CatalogService(tmdb, services['titles'])
    seed = title(1, keywords=())
    seed.source = 'tmdb'
    for expanded in (False, False, True, True):
        _, related = catalog.candidates([seed], 'pt-BR', expanded=expanded)
        assert related.strength(seed.key, 'tmdb:movie:2') == 1
        assert related.strength(seed.key, 'tmdb:movie:3') == .5
    assert tmdb.related.call_count == 2


def test_relevant_results_keep_real_scores_without_previous_five_item_limit(client, post, services):
    post('/profiles', {'name': 'Closest'})
    post('/selection', {'key': 'demo:movie:1'})
    rows = [Recommendation(title(value), 65, {'algorithm_version': 2, 'relevant_evidence': 1,
                                            'related_count': 1, 'genre': 1}, ['Sci-fi']) for value in range(101, 109)]
    rows.append(Recommendation(title(999), 69, {'algorithm_version': 2, 'relevant_evidence': 0}, []))
    with patch.object(services['engine'], 'discover', return_value=rows):
        response = post('/recommendations')
    assert 'id="match-results"' in response.text
    assert response.text.count('class="media-card"') == 8
    assert '65%' in response.text and 'Title 999' not in response.text
    assert 'data-favorite' in response.text and 'data-selection' in response.text
    assert len(services['history'].list(1)[0]['results']) == 8
    post('/language/en-US')
    with patch.object(services['engine'], 'discover', return_value=rows):
        assert 'Chosen for you' in post('/recommendations').text


def test_no_relevant_candidates_shows_change_selection_link_even_with_positive_scores(client, post, services):
    post('/selection', {'key': 'demo:movie:1'})
    irrelevant = Recommendation(title(999), 60, {'relevant_evidence': 0}, [])
    with patch.object(services['engine'], 'discover', return_value=[irrelevant]):
        response = post('/recommendations')
    assert 'Alterar seleção' in response.text
    assert 'class="media-card"' not in response.text
    assert 'id="closest-results"' not in response.text
