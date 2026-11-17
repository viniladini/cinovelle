import sqlite3
from contextlib import contextmanager
from pathlib import Path

SCHEMA = '''
CREATE TABLE IF NOT EXISTS profiles (
 id INTEGER PRIMARY KEY, name TEXT NOT NULL CHECK(length(name) BETWEEN 1 AND 40),
 preferences TEXT NOT NULL DEFAULT '[]');
CREATE TABLE IF NOT EXISTS titles (
 id INTEGER PRIMARY KEY, source TEXT NOT NULL, media_type TEXT NOT NULL CHECK(media_type IN ('movie','tv')),
 external_id INTEGER NOT NULL, title TEXT NOT NULL, payload TEXT NOT NULL,
 updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, UNIQUE(source,media_type,external_id));
CREATE TABLE IF NOT EXISTS genres (id INTEGER PRIMARY KEY, name TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS title_genres (
 title_id INTEGER NOT NULL REFERENCES titles(id) ON DELETE CASCADE,
 genre_id INTEGER NOT NULL REFERENCES genres(id), PRIMARY KEY(title_id,genre_id));
CREATE TABLE IF NOT EXISTS favorites (
 profile_id INTEGER NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
 title_id INTEGER NOT NULL REFERENCES titles(id) ON DELETE CASCADE,
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, PRIMARY KEY(profile_id,title_id));
CREATE TABLE IF NOT EXISTS watchlist (
 id INTEGER PRIMARY KEY,
 profile_id INTEGER NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
 title_id INTEGER NOT NULL REFERENCES titles(id) ON DELETE CASCADE,
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
 UNIQUE(profile_id,title_id));
CREATE TABLE IF NOT EXISTS recommendation_runs (
 id INTEGER PRIMARY KEY, profile_id INTEGER NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
 seeds TEXT NOT NULL, filters TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS recommendation_results (
 run_id INTEGER NOT NULL REFERENCES recommendation_runs(id) ON DELETE CASCADE,
 title_id INTEGER NOT NULL REFERENCES titles(id), score INTEGER NOT NULL CHECK(score BETWEEN 0 AND 100),
 factors TEXT NOT NULL, PRIMARY KEY(run_id,title_id));
CREATE INDEX IF NOT EXISTS idx_runs_profile ON recommendation_runs(profile_id,created_at);
CREATE INDEX IF NOT EXISTS idx_favorites_title ON favorites(title_id);
CREATE INDEX IF NOT EXISTS idx_watchlist_title ON watchlist(title_id);
CREATE INDEX IF NOT EXISTS idx_title_genres_genre ON title_genres(genre_id);
'''


class Database:
    def __init__(self, path: str):
        self._path = path
        Path(path).parent.mkdir(parents=True, exist_ok=True)

    @contextmanager
    def connection(self):
        conn = sqlite3.connect(self._path, timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute('PRAGMA foreign_keys=ON')
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    def initialize(self):
        with self.connection() as conn:
            conn.executescript(SCHEMA)
