from collections import Counter

from app.models import Recommendation
from app.services.affinity import EvidenceScorer
from app.services.match import MatchScorer


class RecommendationEngine:
    """Afinidade heurística determinística; nunca uma probabilidade estatística."""

    def __init__(self, evidence_aware=False, version=1):
        # Modo clássico preserva a reprodução dos cálculos anteriores e sua suíte.
        self.evidence_aware = evidence_aware
        self.version = version

    @staticmethod
    def jaccard(left, right):
        union = left | right
        return len(left & right) / len(union) if union else 0.0

    def factors(self, seed, candidate, related):
        return {
            'genre': self.jaccard(seed.genre_ids(), candidate.genre_ids()),
            'keyword': self.jaccard(seed.keywords, candidate.keywords),
            'related': float(candidate.key in related.get(seed.key, set())),
            'rating': max(0.0, min(1.0, (candidate.rating or 0) / 10)),
        }

    @staticmethod
    def score(factors):
        return max(0, min(100, int(100 * (0.4 * factors['genre'] + 0.25 * factors['keyword']
                                        + 0.25 * factors['related'] + 0.1 * factors['rating']) + 0.5)))

    def recommend(self, seeds, candidates, related=None, media_type='both', genre_id=None, preferences=None):
        seeds = list({item.key: item for item in seeds}.values())
        if not 1 <= len(seeds) <= 5:
            raise ValueError('selection_limit')
        if media_type not in ('both', 'movie', 'tv'):
            raise ValueError('invalid_filter')
        related = related or {}
        candidates = list({item.key: item for item in candidates}.values())
        scorer = (MatchScorer(seeds, candidates, related) if self.version == 2 else
                  EvidenceScorer(seeds, candidates, related) if self.evidence_aware else None)
        selected = {seed.key for seed in seeds}
        genre_counts = Counter(g for seed in seeds for g in seed.genre_ids())
        keyword_counts = Counter(k for seed in seeds for k in seed.keywords)
        recurring_genres = {g for g, count in genre_counts.items() if count > 1}
        recurring_keywords = {k for k, count in keyword_counts.items() if count > 1}
        results = []
        for candidate in {item.key: item for item in candidates}.values():
            if candidate.key in selected or (media_type != 'both' and candidate.media_type != media_type):
                continue
            if genre_id and genre_id not in candidate.genre_ids():
                continue
            if preferences and not candidate.genre_ids().intersection(preferences):
                continue
            shared = [genre.name for genre in candidate.genres if genre.id in genre_counts]
            if scorer:
                factors, score = scorer.evaluate(candidate)
                if self.version == 2:
                    group = scorer.seeds if factors.get('combined_profile') else scorer.groups[int(factors['group_id'])]
                    group_genres = set().union(*(seed.genre_ids() for seed in group))
                    shared = [genre.name for genre in candidate.genres if genre.id in group_genres]
            else:
                individual = [self.factors(seed, candidate, related) for seed in seeds]
                factors = {key: sum(row[key] for row in individual) / len(individual) for key in individual[0]}
                # Compatibilidade com a versão clássica, preservada para reprodução histórica.
                if len(seeds) > 1:
                    for key, recurring, attributes in (
                        ('genre', recurring_genres, candidate.genre_ids()),
                        ('keyword', recurring_keywords, candidate.keywords),
                    ):
                        if recurring:
                            factors[key] = .8 * factors[key] + .2 * self.jaccard(recurring, attributes)
                score = self.score(factors)
            results.append(Recommendation(candidate, score, factors, shared))
        ordered = sorted(results, key=lambda r: (-r.score, r.item.key))
        if self.version != 2:
            return ordered
        ranks, counts = {}, Counter()
        for row in ordered:
            group = row.factors['group_id']
            ranks[row.item.key] = counts[group]
            counts[group] += 1
        return sorted(ordered, key=lambda row: (-row.score, -row.factors.get('reference_count', 0),
                                                ranks[row.item.key], row.item.key))

    def discover(self, catalog, seeds, language, media_type='both', genre_id=None, preferences=None):
        candidates, related = catalog.candidates(seeds, language, media_type, genre_id)
        results = self.recommend(seeds, candidates, related, media_type, genre_id, preferences)
        strong = [result for result in results if result.score >= 70 and result.is_relevant]
        groups = len(MatchScorer(seeds, candidates, related).groups) if self.version == 2 else 1
        covered_groups = {result.factors.get('group_id', 0) for result in strong}
        if not catalog.demo and (len(strong) < 5 or len(covered_groups) < groups):
            from app.integrations import IntegrationError
            try:
                candidates, related = catalog.candidates(seeds, language, media_type, genre_id, expanded=True)
                results = self.recommend(seeds, candidates, related, media_type, genre_id, preferences)
            except IntegrationError:
                pass
        return results

    @staticmethod
    def displayable(results):
        relevant = [result for result in results if result.is_relevant]
        return sorted(relevant, key=lambda row: (-row.score, -row.factors.get('reference_count', 0)))
