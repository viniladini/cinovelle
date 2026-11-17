import time
import unicodedata
from collections import Counter

from app.integrations import IntegrationError
from app.models import Genre, Movie, TVSeries
from app.services.demo import demo_catalog
from app.services.match import RelationEvidence

# IDs semânticos compartilhados entre os vocabulários de filmes e séries do TMDB.
GENRE_CANONICAL = {10765: 878, 10759: 12, 10768: 10752}


def canonical_genre(value):
    return GENRE_CANONICAL.get(value, value)


def normalize(value):
    return ''.join(c for c in unicodedata.normalize('NFD', value.casefold()) if unicodedata.category(c) != 'Mn')


class CatalogService:
    def __init__(self, tmdb, titles, force_demo=False):
        self._tmdb = tmdb
        self._titles = titles
        self.demo = force_demo or not tmdb.configured
        self._details_cache = {}
        self._candidate_cache = {}

    def _convert(self, data, media_type):
        if not isinstance(data, dict) or not isinstance(data.get('id'), int):
            raise IntegrationError('invalid_response')
        cls = Movie if media_type == 'movie' else TVSeries
        for key in ('title', 'name', 'overview', 'release_date', 'first_air_date', 'poster_path', 'backdrop_path', 'imdb_id'):
            if data.get(key) is not None and not isinstance(data[key], str):
                raise IntegrationError('invalid_response')
        for key in ('genres', 'genre_ids'):
            if data.get(key) is not None and not isinstance(data[key], list):
                raise IntegrationError('invalid_response')
        for key in ('keywords', 'external_ids', 'credits'):
            if data.get(key) is not None and not isinstance(data[key], dict):
                raise IntegrationError('invalid_response')
        keywords = data.get('keywords') or {}
        keywords = keywords.get('keywords' if media_type == 'movie' else 'results', []) if isinstance(keywords, dict) else []
        raw_genres = data.get('genres') or []
        if any(not isinstance(g, dict) or not isinstance(g.get('id'), int) or not isinstance(g.get('name'), str) for g in raw_genres):
            raise IntegrationError('invalid_response')
        genres = {canonical_genre(g['id']): g['name'] for g in raw_genres}
        if not isinstance(keywords, list):
            raise IntegrationError('invalid_response')
        cast = (data.get('credits') or {}).get('cast') or []
        if not isinstance(cast, list):
            raise IntegrationError('invalid_response')
        rating = data.get('vote_average')
        count = data.get('vote_count') or 0
        rating = float(rating) if isinstance(rating, (int, float)) and isinstance(count, (int, float)) and count > 0 and 0 <= rating <= 10 else None
        image = lambda path, size: f'https://image.tmdb.org/t/p/{size}{path}' if path else ''
        return cls(external_id=data['id'], title=data.get('title') or data.get('name') or '—',
                   year=(data.get('release_date') or data.get('first_air_date') or '')[:4],
                   overview=data.get('overview') or '', genres=[Genre(g, name) for g, name in genres.items()],
                   keywords={str(k['id']) for k in keywords if isinstance(k, dict) and 'id' in k},
                   keyword_names={str(k['id']): k['name'] for k in keywords
                                  if isinstance(k, dict) and 'id' in k and isinstance(k.get('name'), str)},
                   rating=rating, poster=image(data.get('poster_path'), 'w500'), backdrop=image(data.get('backdrop_path'), 'w1280'),
                   imdb_id=(data.get('external_ids') or {}).get('imdb_id') or data.get('imdb_id') or '',
                   cast=[p['name'] for p in cast[:6] if isinstance(p, dict) and isinstance(p.get('name'), str)],
                   runtime=data.get('runtime') if isinstance(data.get('runtime'), int) else None,
                   seasons=data.get('number_of_seasons') if isinstance(data.get('number_of_seasons'), int) else None, source='tmdb')

    def _search_items(self, rows, kind, language):
        # Resultados resumidos contêm genre_ids, em vez dos objetos dos detalhes.
        genre_names = {g.id: g.name for g in self.genres(language)}
        items = []
        for row in rows:
            media_type = row.get('media_type', kind)
            if media_type not in ('movie', 'tv'):
                continue
            data = row.copy()
            ids = data.get('genre_ids') or []
            if not isinstance(ids, list) or any(not isinstance(value, int) for value in ids):
                raise IntegrationError('invalid_response')
            data['genres'] = [{'id': canonical_genre(value), 'name': genre_names[canonical_genre(value)]}
                              for value in ids if canonical_genre(value) in genre_names]
            items.append(self._convert(data, media_type))
        return items

    def get(self, key, language='pt-BR'):
        try:
            source, kind, external_id = key.split(':')
            external_id = int(external_id)
            if source not in ('demo', 'tmdb') or kind not in ('movie', 'tv') or external_id < 1:
                raise ValueError
        except (ValueError, AttributeError):
            raise LookupError('not_found') from None
        if source == 'demo':
            item = next((i for i in demo_catalog(language) if i.key == key), None)
            if not item:
                raise LookupError('not_found')
        else:
            cached = self._details_cache.get((key, language))
            if cached and cached[0] > time.monotonic():
                return cached[1]
            try:
                item = self._convert(self._tmdb.details(kind, external_id, language), kind)
            except IntegrationError:
                # Um título já persistido ainda pode ser aberto sem conexão.
                item = self._titles.get(source, kind, external_id)
                if item is None:
                    raise
            if len(self._details_cache) >= 256:
                self._details_cache.clear()
            self._details_cache[(key, language)] = (time.monotonic() + 1800, item)
        self._titles.save(item)
        return item

    def search(self, query='', language='pt-BR', media_type='both'):
        if self.demo:
            return [i for i in demo_catalog(language) if normalize(query) in normalize(i.title)
                    and (media_type == 'both' or i.media_type == media_type)]
        if not query.strip():
            items = []
            for kind in (('movie', 'tv') if media_type == 'both' else (media_type,)):
                data = self._tmdb.discover(kind, [], language)
                items.extend(self._search_items(data, kind, language))
            return items
        data = self._tmdb.search(query, language, 'multi' if media_type == 'both' else media_type)
        return self._search_items(data, media_type, language)

    def genres(self, language):
        if self.demo:
            return sorted({g.id: g for item in demo_catalog(language) for g in item.genres}.values(), key=lambda g: g.name)
        values = {}
        for kind in ('movie', 'tv'):
            for row in self._tmdb.genres(kind, language):
                if not isinstance(row.get('name'), str):
                    raise IntegrationError('invalid_response')
                value = canonical_genre(row['id'])
                values.setdefault(value, Genre(value, row['name']))
        return sorted(values.values(), key=lambda g: g.name)

    def watch_providers(self, key, language='pt-BR'):
        item = self.get(key, language)
        return (dict(region='BR', groups=[], link='') if item.source == 'demo' else
                self._tmdb.watch_providers(item.media_type, item.external_id))

    def ensure_imdb_id(self, item, language):
        if item.source == 'tmdb' and not item.imdb_id:
            data = self._tmdb.external_ids(item.media_type, item.external_id, language)
            if isinstance(data.get('imdb_id'), str):
                item.imdb_id = data['imdb_id']
                self._titles.save(item)
        return item.imdb_id

    def candidates(self, seeds, language, media_type='both', genre_id=None, expanded=False):
        if all(seed.source == 'demo' for seed in seeds):
            return demo_catalog(language), {}
        cache_key = (tuple(sorted(seed.key for seed in seeds)), language, media_type, genre_id)
        previous = self._candidate_cache.get(cache_key)
        if previous and previous['expires'] <= time.monotonic():
            previous = None
        if previous and (not expanded or previous['expanded']):
            return list(previous['items']), RelationEvidence(previous['related'], sources=previous['related'].sources)
        pool = dict(previous['pool']) if previous else {}
        related = RelationEvidence(previous['related'], sources=previous['related'].sources) if previous else RelationEvidence()
        hints = dict(previous['hints']) if previous else {}
        failures = []
        retrievals = 0

        def collect(kind, fetch, seed=None, thematic=False, source=None):
            nonlocal retrievals
            if retrievals >= 22:
                return
            retrievals += 1
            try:
                rows = fetch()
                if seed:
                    related.setdefault(seed.key, set()).update(f'tmdb:{kind}:{row["id"]}' for row in rows)
                    related.sources.setdefault(seed.key, {}).setdefault(source, set()).update(
                        f'tmdb:{kind}:{row["id"]}' for row in rows)
                for index, row in enumerate(rows):
                    key = f'tmdb:{kind}:{row["id"]}'
                    hint = (1.0 if thematic or source == 'recommendations' else .5 if seed else .25) / (1 + index / 5)
                    hints[key] = max(hints.get(key, 0), hint)
                    if key not in pool and len(pool) < 400:
                        pool[key] = (kind, row)
            except IntegrationError as error:
                failures.append(error)

        kinds = ('movie', 'tv') if media_type == 'both' else (media_type,)
        counts = Counter(value for seed in seeds for value in seed.genre_ids())
        top_genres = {genre_id} if genre_id else set(sorted(counts, key=lambda value: (-counts[value], value))[:3])
        keyword_counts = Counter(value for seed in seeds for value in seed.keywords if value.isdigit())
        from app.services.match import keyword_importance
        importance = {seed.key: keyword_importance(seed) for seed in seeds}

        def keyword_priority(value):
            centrality = sum(profile.get(value, 0) for profile in importance.values())
            return -keyword_counts[value], -centrality, value

        top_keywords = sorted(keyword_counts, key=keyword_priority)[:6]

        def mapped_genres(kind, values):
            return {({878: 10765, 12: 10759, 10752: 10768}.get(g, g) if kind == 'tv' else g) for g in values}

        if not previous:
            for seed in sorted(seeds, key=lambda item: item.key):
                if seed.source == 'tmdb':
                    for endpoint in ('recommendations', 'similar'):
                        collect(seed.media_type, lambda: self._tmdb.related(
                            seed.media_type, seed.external_id, language, endpoint), seed, source=endpoint)
            for kind in kinds:
                if top_genres:
                    collect(kind, lambda: self._tmdb.discover(kind, mapped_genres(kind, top_genres), language))
                if len(top_keywords) >= 2:
                    collect(kind, lambda: self._tmdb.discover(kind, set(), language,
                                                             keyword_ids=top_keywords[:2], match_all=True), thematic=True)
        if expanded:
            # Combinações por referência preservam interesses minoritários de uma seleção heterogênea.
            combinations = []
            for seed in sorted(seeds, key=lambda item: item.key):
                keywords = tuple(sorted((value for value in seed.keywords if value.isdigit()),
                                        key=keyword_priority)[2:4])
                genre_values = tuple(sorted(seed.genre_ids())[:2])
                if keywords or genre_values:
                    combinations.append((genre_values, keywords))
            for kind in kinds:
                for genre_values, keywords in list(dict.fromkeys(combinations))[:3]:
                    collect(kind, lambda: self._tmdb.discover(kind, set() if keywords else mapped_genres(kind, genre_values), language,
                                                             keyword_ids=keywords, match_all=True), thematic=True)
                if top_genres:
                    collect(kind, lambda: self._tmdb.discover(kind, mapped_genres(kind, top_genres), language,
                                                             keyword_ids=top_keywords, page=2))

        from app.services.match import cosine, tokens
        from app.services.themes import concepts, profile
        seed_concepts = [profile(seed) for seed in seeds]
        def priority(key):
            kind, row = pool[key]
            values = {canonical_genre(value) for value in row.get('genre_ids', [])}
            summary = tokens(row.get('overview') or '')
            matches = [len(values & seed.genre_ids()) / max(1, len(seed.genre_ids()))
                       + cosine(summary, tokens(seed.overview)) for seed in seeds]
            relations = sum(key in values for values in related.values())
            topics = concepts(row.get('overview') or '')
            coverage = sum(bool(topics & values.keys()) for values in seed_concepts) / len(seeds)
            return -(hints.get(key, 0) + .5 * relations + .25 * max(matches, default=0) + .5 * coverage), key

        items = list(previous['items']) if previous else []
        attempted = set(previous['attempted']) if previous else set()
        selected = {seed.key for seed in seeds}
        keys = sorted((key for key in pool if key not in selected and key not in attempted
                       and (media_type == 'both' or pool[key][0] == media_type)), key=priority)
        # Considera também o tipo oposto antes de hidratar, sem alterar a afinidade calculada.
        if media_type == 'both':
            seed_types = {seed.media_type for seed in seeds}
            if len(seed_types) == 1:
                cross = [key for key in keys if pool[key][0] not in seed_types
                         and any(len({canonical_genre(value) for value in pool[key][1].get('genre_ids', [])}
                                     & seed.genre_ids()) >= min(2, len(seed.genre_ids()))
                                 for seed in seeds if seed.genres)][:8 if not expanded else 16]
                same = [key for key in keys if pool[key][0] in seed_types]
                keys = [*cross, *same, *(key for key in keys if key not in cross and key not in same)]
        for key in keys:
            if len(attempted) >= (64 if expanded else 32):
                break
            attempted.add(key)
            try:
                items.append(self.get(key, language))
            except (IntegrationError, LookupError) as error:
                failures.append(error)
                if isinstance(error, IntegrationError) and error.code == 'rate_limit':
                    break
        if not items and failures:
            raise failures[0]
        if len(self._candidate_cache) >= 32:
            self._candidate_cache.clear()
        self._candidate_cache[cache_key] = dict(expires=time.monotonic() + 300, expanded=expanded,
                                               items=list(items), related=related, pool=pool, attempted=attempted, hints=hints)
        return items, related
