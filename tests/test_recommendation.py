import pytest

from app.models import Genre, Movie, TVSeries
from app.services.demo import demo_catalog
from app.services.recommendation import RecommendationEngine


def test_exact_formula_and_rating_cap():
    engine = RecommendationEngine()
    seed = Movie(1, 'A', genres=[Genre(18, 'Drama')], keywords={'a'})
    same = Movie(2, 'B', genres=seed.genres, keywords={'a'}, rating=10)
    result = engine.recommend([seed], [same], {seed.key: {same.key}})[0]
    assert result.score == 100
    incompatible = Movie(3, 'C', genres=[Genre(35, 'Comedy')], rating=10)
    assert engine.recommend([seed], [incompatible])[0].score == 10


def test_single_multiple_dedup_exclusion_determinism():
    engine = RecommendationEngine()
    items = demo_catalog()
    seeds = [items[0], items[3]]
    result = engine.recommend(seeds, items + items)
    assert len(result) == len(items) - 2
    assert {r.item.key for r in result}.isdisjoint({i.key for i in seeds})
    assert [r.score for r in result] == sorted([r.score for r in result], reverse=True)
    assert [(r.item.key, r.score) for r in result] == [(r.item.key, r.score) for r in engine.recommend(seeds, reversed(items))]
    assert all(0 <= f <= 1 for r in result for f in r.factors.values())


def test_recurring_rule():
    engine = RecommendationEngine()
    a = Movie(1, 'A', genres=[Genre(18, 'Drama'), Genre(35, 'Comedy')], keywords={'x','y'})
    b = Movie(2, 'B', genres=[Genre(18, 'Drama')], keywords={'x'})
    c = TVSeries(3, 'C', genres=[Genre(18, 'Drama')], keywords={'x'})
    result = engine.recommend([a, b], [c])[0]
    assert result.factors['genre'] == pytest.approx(.8 * .75 + .2)
    assert result.factors['keyword'] == pytest.approx(.8 * .75 + .2)
    assert result.score == 52


def test_filters_and_cross_type():
    items = demo_catalog()
    engine = RecommendationEngine()
    result = engine.recommend(items[:1], items, media_type='tv', genre_id=18)
    assert result and all(r.item.media_type == 'tv' and 18 in r.item.genre_ids() for r in result)
    assert all(878 in r.item.genre_ids() for r in engine.recommend(items[:1], items, preferences=[878]))


def test_missing_data_and_limits():
    engine = RecommendationEngine()
    a, b = Movie(1, 'A'), TVSeries(2, 'B')
    assert engine.recommend([a], [b])[0].score == 0
    assert engine.jaccard(set(), set()) == 0
    assert engine.recommend([a], []) == []
    for seeds in ([], demo_catalog()[:6]):
        with pytest.raises(ValueError):
            engine.recommend(seeds, [])
    with pytest.raises(ValueError):
        engine.recommend([a], [], media_type='invalid')
