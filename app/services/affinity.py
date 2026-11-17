"""Cálculo de afinidade com disponibilidade e confiabilidade explícitas."""
from collections import Counter
from math import fsum, log


class EvidenceScorer:
    WEIGHTS = {'genre': .40, 'keyword': .25, 'related': .25}

    def __init__(self, seeds, candidates, related):
        self.seeds = seeds
        self.related = related
        documents = {item.key: item for item in [*seeds, *candidates]}
        frequency = Counter(word for item in documents.values() for word in item.keywords)
        self.idf = {word: 1 + log((1 + len(documents)) / (1 + count)) for word, count in frequency.items()}

    @staticmethod
    def profile(sets):
        known = [values for values in sets if values]
        counts = Counter(value for values in known for value in values)
        return {value: count / len(known) for value, count in counts.items()}

    @staticmethod
    def similarity(profile, values, weights=None, overlap=False):
        weights = weights or {}
        union = sorted(set(profile) | values)
        intersection = fsum(min(profile.get(key, 0), float(key in values)) * weights.get(key, 1) for key in union)
        total = fsum(max(profile.get(key, 0), float(key in values)) * weights.get(key, 1) for key in union)
        jaccard = intersection / total if total else 0
        if not overlap:
            return jaccard
        shorter = min(fsum(profile.values()), len(values))
        coefficient = intersection / shorter if shorter else 0
        return (jaccard + coefficient) / 2

    def evaluate(self, candidate):
        genre_profile = self.profile([item.genre_ids() for item in self.seeds])
        keyword_profile = self.profile([item.keywords for item in self.seeds])
        genre_known = bool(genre_profile and candidate.genres)
        keyword_known = bool(keyword_profile and candidate.keywords)
        # Endpoints do mesmo tipo não fornecem evidência negativa para cruzamento movie/tv.
        relations = [float(candidate.key in self.related[seed.key]) for seed in self.seeds
                     if seed.key in self.related and seed.media_type == candidate.media_type]
        available = {'genre': genre_known, 'keyword': keyword_known, 'related': bool(relations)}
        factors = {
            'genre': self.similarity(genre_profile, candidate.genre_ids(), overlap=True),
            'keyword': self.similarity(keyword_profile, candidate.keywords, self.idf),
            'related': sum(relations) / len(relations) if relations else 0,
            'rating': max(0, min(1, candidate.rating / 10)) if candidate.rating is not None else 0,
        }
        active_weight = sum(weight for key, weight in self.WEIGHTS.items() if available[key])
        signal_count = sum(available.values())
        # Três atributos comparáveis e duas famílias de evidência dão confiança integral.
        # Com uma só família, conserva sua participação original (sem renormalização inflacionária).
        units = []
        for seed in self.seeds:
            units.append(min(len(seed.genre_ids()), len(candidate.genre_ids()))
                         + min(len(seed.keywords), len(candidate.keywords))
                         + int(candidate.key in self.related.get(seed.key, set())))
        reliability = min(1, fsum(min(1, count / 3) for count in units) / len(units))
        content_weight = .9 if candidate.rating is not None else 1
        if signal_count < 2:
            reliability = min(reliability, active_weight / content_weight)
        content = (sum(self.WEIGHTS[key] * factors[key] for key in self.WEIGHTS if available[key])
                   / active_weight if active_weight else 0)
        # A nota mantém teto de dez pontos, inclusive sem qualquer atributo de conteúdo.
        value = content_weight * content * reliability + .1 * factors['rating']
        factors.update(reliability=reliability, coverage=active_weight / .9,
                       genre_available=float(genre_known), keyword_available=float(keyword_known),
                       related_available=float(bool(relations)), rating_available=float(candidate.rating is not None),
                       algorithm_version=1.0)
        return factors, max(0, min(100, int(value * 100 + .5)))
