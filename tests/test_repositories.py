import sqlite3

import pytest

from app import create_app
from app.models import Profile
from app.services.demo import demo_catalog


def test_schema_foreign_keys_and_title_identity(services):
    db = services['db']
    with db.connection() as conn:
        tables = {r['name'] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert {'profiles','titles','genres','title_genres','favorites','recommendation_runs','recommendation_results','watchlist'} <= tables
        assert conn.execute('PRAGMA foreign_keys').fetchone()[0] == 1
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute('INSERT INTO favorites(profile_id,title_id) VALUES(999,999)')
    movie, series = demo_catalog()[0], demo_catalog()[2]
    series.external_id = movie.external_id
    a, b = services['titles'].save(movie), services['titles'].save(series)
    assert a != b
    assert services['titles'].save(movie) == a
    with db.connection() as conn:
        assert conn.execute('SELECT COUNT(*) FROM title_genres WHERE title_id=?', (a,)).fetchone()[0] == 2


def test_profile_crud_and_encapsulation(services):
    repo = services['profiles']
    profile = repo.create('  Marina  ')
    assert repo.get(profile.id).name == 'Marina'
    repo.update(profile.id, 'Lia', [18, 35])
    loaded = repo.get(profile.id)
    loaded.preferences.append(878)
    assert loaded.preferences == [18, 35]
    assert [p.name for p in repo.all()] == ['Lia']
    repo.delete(profile.id)
    assert repo.get(profile.id) is None
    with pytest.raises(ValueError):
        Profile(1, ' ')
    with pytest.raises(ValueError):
        repo.create('x' * 41)


def test_favorites_crud_and_cascade(services):
    p = services['profiles'].create('Teste')
    item = demo_catalog()[0]
    title_id = services['titles'].save(item)
    repo = services['favorites']
    repo.add(p.id, title_id)
    repo.add(p.id, title_id)
    assert [i.key for i in repo.list(p.id)] == [item.key]
    repo.remove(p.id, title_id)
    assert repo.list(p.id) == []
    repo.add(p.id, title_id)
    services['profiles'].delete(p.id)
    assert repo.list(p.id) == []


def test_history_crud_ownership_and_cascade(services):
    p = services['profiles'].create('A')
    other = services['profiles'].create('B')
    items = demo_catalog()
    results = services['engine'].recommend(items[:1], items)
    history = services['history']
    run = history.create(p.id, [{'key': items[0].key, 'title': items[0].title}], {'type': 'both'}, results, services['titles'])
    assert len(history.list(p.id)[0]['results']) == 17
    history.delete(other.id, run)
    assert len(history.list(p.id)) == 1
    history.delete(p.id, run)
    assert history.list(p.id) == []
    history.create(p.id, [], {}, results, services['titles'])
    services['profiles'].delete(p.id)
    with services['db'].connection() as conn:
        assert conn.execute('SELECT COUNT(*) FROM recommendation_results').fetchone()[0] == 0


def test_persistence_and_cache_update(app, services):
    p = services['profiles'].create('Persistente')
    item = demo_catalog()[0]
    item.title = 'Atualizado'
    title_id = services['titles'].save(item)
    services['favorites'].add(p.id, title_id)
    other = create_app(dict(app.config))
    repos = other.extensions['cinovelle']
    assert repos['profiles'].get(p.id).name == 'Persistente'
    assert repos['favorites'].list(p.id)[0].title == 'Atualizado'


def test_transaction_rolls_back(services):
    with pytest.raises(RuntimeError):
        with services['db'].connection() as conn:
            conn.execute('INSERT INTO profiles(name) VALUES(?)', ('Rollback',))
            raise RuntimeError
    assert services['profiles'].all() == []


def test_legacy_award_data_survives_non_destructive_initialization(services):
    title_id = services['titles'].save(demo_catalog()[0])
    with services['db'].connection() as conn:
        conn.execute('CREATE TABLE awards(id INTEGER PRIMARY KEY,title_id INTEGER REFERENCES titles(id),category TEXT)')
        conn.execute('INSERT INTO awards(title_id,category) VALUES(?,?)', (title_id, 'Legacy'))
    services['db'].initialize()
    with services['db'].connection() as conn:
        assert conn.execute('SELECT category FROM awards').fetchone()[0] == 'Legacy'
