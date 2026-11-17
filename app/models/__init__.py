from dataclasses import dataclass, field


@dataclass(frozen=True)
class Genre:
    id: int
    name: str


@dataclass
class MediaItem:
    external_id: int
    title: str
    year: str = ''
    overview: str = ''
    genres: list[Genre] = field(default_factory=list)
    keywords: set[str] = field(default_factory=set)
    rating: float | None = None
    poster: str = ''
    backdrop: str = ''
    imdb_id: str = ''
    cast: list[str] = field(default_factory=list)
    source: str = 'demo'
    media_type: str = field(default='', init=False)
    runtime: int | None = None
    seasons: int | None = None
    keyword_names: dict[str, str] = field(default_factory=dict)

    @property
    def key(self) -> str:
        return f'{self.source}:{self.media_type}:{self.external_id}'

    def genre_ids(self) -> set[int]:
        return {genre.id for genre in self.genres}

    def duration(self) -> int | None:
        raise NotImplementedError


@dataclass
class Movie(MediaItem):
    media_type: str = field(default='movie', init=False)

    def duration(self) -> int | None:
        return self.runtime


@dataclass
class TVSeries(MediaItem):
    media_type: str = field(default='tv', init=False)

    def duration(self) -> int | None:
        return self.seasons


class Profile:
    def __init__(self, profile_id: int, name: str, preferences: list[int] | None = None):
        self.id = profile_id
        self.rename(name)
        self._preferences = list(preferences or [])

    @property
    def name(self) -> str:
        return self._name

    @property
    def preferences(self) -> list[int]:
        return self._preferences.copy()

    def rename(self, name: str) -> None:
        name = name.strip()
        if not 1 <= len(name) <= 40:
            raise ValueError('invalid_name')
        self._name = name


@dataclass
class Recommendation:
    item: MediaItem
    score: int
    factors: dict[str, float]
    shared_genres: list[str]

    @property
    def tier(self):
        return 'exceptional' if self.score >= 90 else 'very_high' if self.score >= 80 else 'good' if self.score >= 70 else 'limited'

    @property
    def is_relevant(self):
        return bool(self.factors.get('relevant_evidence', self.score >= 70))

    @property
    def explanation_keys(self):
        keys = []
        if self.factors.get('reference_count', 0) >= 2 and self.factors.get('shared_concepts', 0) >= 2:
            keys.append('reason_combined')
        units = self.factors.get('thematic_units', max(self.factors.get('shared_keywords', 0),
                                                      self.factors.get('shared_themes', 0)))
        if self.factors.get('keyword', 0) >= .45 and units >= 2:
            keys.append('reason_themes')
        if self.factors.get('overview', 0) >= .35 and self.factors.get('shared_words', 0) >= 4:
            keys.append('reason_narrative')
        if self.factors.get('related_count', 0):
            keys.append('reason_relations')
        if self.factors.get('genre', 0) >= .5 and self.shared_genres:
            keys.append('reason_genres')
        return keys
