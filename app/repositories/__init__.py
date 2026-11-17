import json
from dataclasses import asdict

from app.models import Genre, Movie, Profile, TVSeries


def serialize(item):
    data = asdict(item)
    data['keywords'] = sorted(item.keywords)
    return json.dumps(data, ensure_ascii=False)


def deserialize(payload):
    data = json.loads(payload)
    cls = Movie if data.pop('media_type') == 'movie' else TVSeries
    data['genres'] = [Genre(**genre) for genre in data['genres']]
    data['keywords'] = set(data['keywords'])
    return cls(**data)


class Repository:
    def __init__(self, database):
        self._db = database


class TitleRepository(Repository):
    def save(self, item):
        with self._db.connection() as conn:
            conn.execute('''INSERT INTO titles(source,media_type,external_id,title,payload)
                VALUES(?,?,?,?,?) ON CONFLICT(source,media_type,external_id) DO UPDATE SET
                title=excluded.title,payload=excluded.payload,updated_at=CURRENT_TIMESTAMP''',
                (item.source, item.media_type, item.external_id, item.title, serialize(item)))
            title_id = conn.execute('SELECT id FROM titles WHERE source=? AND media_type=? AND external_id=?',
                                    (item.source, item.media_type, item.external_id)).fetchone()['id']
            conn.execute('DELETE FROM title_genres WHERE title_id=?', (title_id,))
            for genre in item.genres:
                conn.execute('INSERT INTO genres(id,name) VALUES(?,?) ON CONFLICT(id) DO UPDATE SET name=excluded.name',
                             (genre.id, genre.name))
                conn.execute('INSERT INTO title_genres VALUES(?,?)', (title_id, genre.id))
            return title_id

    def get(self, source, media_type, external_id):
        with self._db.connection() as conn:
            row = conn.execute('SELECT payload FROM titles WHERE source=? AND media_type=? AND external_id=?',
                               (source, media_type, external_id)).fetchone()
        return deserialize(row['payload']) if row else None

    def all(self, source=None):
        with self._db.connection() as conn:
            rows = conn.execute('SELECT payload FROM titles WHERE (? IS NULL OR source=?) ORDER BY id',
                                (source, source)).fetchall()
        return [deserialize(row['payload']) for row in rows]


class ProfileRepository(Repository):
    def create(self, name):
        profile = Profile(0, name)
        with self._db.connection() as conn:
            profile.id = conn.execute('INSERT INTO profiles(name) VALUES(?)', (profile.name,)).lastrowid
        return profile

    def get(self, profile_id):
        with self._db.connection() as conn:
            row = conn.execute('SELECT * FROM profiles WHERE id=?', (profile_id,)).fetchone()
        return Profile(row['id'], row['name'], json.loads(row['preferences'])) if row else None

    def all(self):
        with self._db.connection() as conn:
            rows = conn.execute('SELECT * FROM profiles ORDER BY id').fetchall()
        return [Profile(row['id'], row['name'], json.loads(row['preferences'])) for row in rows]

    def update(self, profile_id, name, preferences):
        profile = Profile(profile_id, name, preferences)
        with self._db.connection() as conn:
            conn.execute('UPDATE profiles SET name=?,preferences=? WHERE id=?',
                         (profile.name, json.dumps(profile.preferences), profile.id))

    def delete(self, profile_id):
        with self._db.connection() as conn:
            conn.execute('DELETE FROM profiles WHERE id=?', (profile_id,))


class FavoriteRepository(Repository):
    def add(self, profile_id, title_id):
        with self._db.connection() as conn:
            conn.execute('INSERT OR IGNORE INTO favorites(profile_id,title_id) VALUES(?,?)', (profile_id, title_id))

    def remove(self, profile_id, title_id):
        with self._db.connection() as conn:
            conn.execute('DELETE FROM favorites WHERE profile_id=? AND title_id=?', (profile_id, title_id))

    def list(self, profile_id):
        with self._db.connection() as conn:
            rows = conn.execute('''SELECT t.payload FROM favorites f JOIN titles t ON t.id=f.title_id
                WHERE profile_id=? ORDER BY f.created_at DESC,t.id''', (profile_id,)).fetchall()
        return [deserialize(row['payload']) for row in rows]


class WatchlistRepository(Repository):
    def add(self, profile_id, title_id):
        with self._db.connection() as conn:
            conn.execute('INSERT OR IGNORE INTO watchlist(profile_id,title_id) VALUES(?,?)', (profile_id, title_id))

    def remove(self, profile_id, title_id):
        with self._db.connection() as conn:
            conn.execute('DELETE FROM watchlist WHERE profile_id=? AND title_id=?', (profile_id, title_id))

    def list(self, profile_id):
        with self._db.connection() as conn:
            rows = conn.execute('''SELECT t.payload FROM watchlist w JOIN titles t ON t.id=w.title_id
                WHERE w.profile_id=? ORDER BY w.created_at DESC,w.id DESC''', (profile_id,)).fetchall()
        return [deserialize(row['payload']) for row in rows]


class HistoryRepository(Repository):
    def create(self, profile_id, seeds, filters, results, titles):
        # Os títulos são persistidos antes; a execução e todos os resultados são atômicos.
        ids = [(titles.save(result.item), result) for result in results]
        with self._db.connection() as conn:
            run_id = conn.execute('INSERT INTO recommendation_runs(profile_id,seeds,filters) VALUES(?,?,?)',
                                  (profile_id, json.dumps(seeds), json.dumps(filters))).lastrowid
            conn.executemany('INSERT INTO recommendation_results VALUES(?,?,?,?)',
                             [(run_id, title_id, result.score, json.dumps(result.factors)) for title_id, result in ids])
        return run_id

    def list(self, profile_id):
        with self._db.connection() as conn:
            runs = [dict(row) for row in conn.execute('SELECT * FROM recommendation_runs WHERE profile_id=? ORDER BY id DESC', (profile_id,))]
            for run in runs:
                run['seeds'] = json.loads(run['seeds'])
                run['filters'] = json.loads(run['filters'])
                run['results'] = [dict(row) for row in conn.execute('''SELECT t.payload,r.score FROM recommendation_results r
                    JOIN titles t ON t.id=r.title_id WHERE run_id=? ORDER BY score DESC,t.id''', (run['id'],))]
                for result in run['results']:
                    result['item'] = deserialize(result.pop('payload'))
        return runs

    def delete(self, profile_id, run_id=None):
        with self._db.connection() as conn:
            conn.execute('DELETE FROM recommendation_runs WHERE profile_id=? AND (? IS NULL OR id=?)',
                         (profile_id, run_id, run_id))
