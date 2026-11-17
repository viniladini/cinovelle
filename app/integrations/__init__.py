import copy
import re
import time

import requests


class IntegrationError(Exception):
    """Falha recuperável de um provedor, sem expor credenciais na interface."""

    def __init__(self, code):
        super().__init__(code)
        self.code = code


class JSONClient:
    def __init__(self, session=None, ttl=1800):
        self._session = session or requests.Session()
        self._cache = {}
        self._ttl = ttl

    def _get(self, url, params, headers=None):
        key = (url, tuple(sorted(params.items())))
        cached = self._cache.get(key)
        if cached and cached[0] > time.monotonic():
            return copy.deepcopy(cached[1])
        try:
            response = self._session.get(url, params=params, headers=headers or {}, timeout=(3, 8))
            code = response.status_code
            if code in (401, 403):
                raise IntegrationError('credentials')
            if code == 404:
                raise IntegrationError('not_found')
            if code == 429:
                raise IntegrationError('rate_limit')
            if code >= 500:
                raise IntegrationError('provider')
            response.raise_for_status()
            data = response.json()
            if not isinstance(data, dict):
                raise IntegrationError('invalid_response')
        except requests.Timeout:
            raise IntegrationError('timeout') from None
        except (requests.RequestException, ValueError):
            raise IntegrationError('provider') from None
        if len(self._cache) >= 512:
            self._cache.clear()
        self._cache[key] = (time.monotonic() + self._ttl, data)
        return copy.deepcopy(data)


class TMDBClient(JSONClient):
    BASE = 'https://api.themoviedb.org/3'

    def __init__(self, api_key='', token='', session=None):
        super().__init__(session)
        self._api_key = api_key
        self._token = token

    @property
    def configured(self):
        return bool(self._api_key or self._token)

    def get(self, path, language='pt-BR', **params):
        if not self.configured:
            raise IntegrationError('credentials')
        headers = {'Authorization': f'Bearer {self._token}'} if self._token else {}
        if not self._token:
            params['api_key'] = self._api_key
        params['language'] = language
        return self._get(self.BASE + path, params, headers)

    @staticmethod
    def _list(data, key):
        rows = data.get(key, [])
        if not isinstance(rows, list) or any(not isinstance(row, dict) or not isinstance(row.get('id'), int) for row in rows):
            raise IntegrationError('invalid_response')
        return rows

    def search(self, query, language='pt-BR', media_type='multi'):
        if media_type not in ('multi', 'movie', 'tv'):
            raise ValueError('media_type')
        return self._list(self.get(f'/search/{media_type}', language, query=query, include_adult='false'), 'results')

    def details(self, media_type, external_id, language):
        data = self.get(f'/{media_type}/{external_id}', language,
                        append_to_response='keywords,external_ids,credits')
        if 'keywords' not in data:
            # Alguns retornos parciais omitem o append. Uma lista vazia válida não exige nova consulta.
            try:
                rows = self.keywords(media_type, external_id, language)
                data['keywords'] = {'keywords' if media_type == 'movie' else 'results': rows}
            except IntegrationError:
                pass  # Metadados opcionais indisponíveis reduzem a confiabilidade do cálculo.
        return data

    def related(self, media_type, external_id, language, kind='recommendations'):
        if kind not in ('recommendations', 'similar'):
            raise ValueError('kind')
        return self._list(self.get(f'/{media_type}/{external_id}/{kind}', language), 'results')

    def discover(self, media_type, genre_ids, language, *, keyword_ids=(), match_all=False, page=1):
        if media_type not in ('movie', 'tv') or not 1 <= page <= 2:
            raise ValueError('invalid_filter')
        separator = ',' if match_all else '|'
        params = dict(with_genres=separator.join(map(str, sorted(genre_ids))),
                      sort_by='popularity.desc', include_adult='false', page=page)
        if keyword_ids:
            params['with_keywords'] = separator.join(map(str, sorted(keyword_ids)))
        return self._list(self.get(f'/discover/{media_type}', language, **params), 'results')

    def genres(self, media_type, language):
        return self._list(self.get(f'/genre/{media_type}/list', language), 'genres')

    def keywords(self, media_type, external_id, language):
        data = self.get(f'/{media_type}/{external_id}/keywords', language)
        return self._list(data, 'keywords' if media_type == 'movie' else 'results')

    def external_ids(self, media_type, external_id, language):
        return self.get(f'/{media_type}/{external_id}/external_ids', language)

    def watch_providers(self, media_type, external_id, region='BR'):
        if media_type not in ('movie', 'tv') or region != 'BR':
            raise ValueError('invalid_filter')
        data = self.get(f'/{media_type}/{external_id}/watch/providers')
        results = data.get('results', {})
        if not isinstance(results, dict) or not isinstance(results.get(region, {}), dict):
            raise IntegrationError('invalid_response')
        country = results.get(region, {})
        groups = []
        for kind in ('flatrate', 'free', 'ads', 'rent', 'buy'):
            values = country.get(kind, [])
            if not isinstance(values, list):
                raise IntegrationError('invalid_response')
            providers = []
            seen = set()
            for row in values:
                if (not isinstance(row, dict) or not isinstance(row.get('provider_id'), int)
                        or not isinstance(row.get('provider_name'), str) or not row['provider_name'].strip()):
                    raise IntegrationError('invalid_response')
                if row['provider_id'] in seen:
                    continue
                seen.add(row['provider_id'])
                logo = row.get('logo_path')
                providers.append(dict(name=row['provider_name'], logo=f'https://image.tmdb.org/t/p/w92{logo}'
                                      if isinstance(logo, str) and logo.startswith('/') else ''))
            if providers:
                groups.append(dict(kind=kind, providers=providers))
        link = country.get('link', '')
        from urllib.parse import urlparse
        parsed = urlparse(link) if isinstance(link, str) else None
        link = link if parsed and parsed.scheme == 'https' and parsed.hostname in ('www.themoviedb.org', 'themoviedb.org') else ''
        return dict(region=region, groups=groups, link=link)


class OMDbClient(JSONClient):
    def __init__(self, api_key='', session=None):
        super().__init__(session, ttl=86400)
        self._api_key = api_key

    @property
    def configured(self):
        return bool(self._api_key)

    @staticmethod
    def parsed_rating(data):
        if data.get('Response') == 'False':
            return None
        try:
            rating = float(data.get('imdbRating'))
            return rating if 0 <= rating <= 10 else None
        except (ValueError, TypeError):
            return None

    def cached_rating(self, imdb_id):
        if not self.configured or not isinstance(imdb_id, str) or not re.fullmatch(r'tt\d{5,12}', imdb_id):
            return None
        key = ('https://www.omdbapi.com/', tuple(sorted({'apikey': self._api_key, 'i': imdb_id}.items())))
        cached = self._cache.get(key)
        return self.parsed_rating(cached[1]) if cached and cached[0] > time.monotonic() else None

    def rating(self, imdb_id):
        if not self._api_key or not isinstance(imdb_id, str) or not re.fullmatch(r'tt\d{5,12}', imdb_id):
            return None
        data = self._get('https://www.omdbapi.com/', {'apikey': self._api_key, 'i': imdb_id})
        if data.get('Response') == 'False':
            if 'key' in str(data.get('Error', '')).lower():
                raise IntegrationError('credentials')
            return None
        return self.parsed_rating(data)
