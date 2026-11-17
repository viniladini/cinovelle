"""Cinovelle Match v2: perfis por interesse e evidência auditável, sem serviços externos."""
from collections import Counter
from math import fsum, log, sqrt
import re
import unicodedata

from app.services.affinity import EvidenceScorer
from app.services.themes import profile as thematic_profile, narrative_terms


STOPWORDS = set('''the and for that with from this are was were has have had his her their they them
into when who what which while about after before through over under out will can not but its
she him you your our one two more most some than then there where being been upon must finds
uma umas uns um de da do das dos em no na nos nas que com por para como ao aos e o a os as
se seu sua seus suas ele ela eles elas um ser sao foi eram era tem ter pelo pela entre mais
quando onde sobre ate apos antes durante enquanto descobre encontra precisa anos vida'''.split())

NON_NARRATIVE_KEYWORDS = {'independent film', 'woman director', 'directorial debut', "director's cut",
                          'based on novel or book', 'based on short story', 'based on comic', 'based on true story',
                          'remake', 'sequel', 'prequel', 'duringcreditsstinger', 'aftercreditsstinger',
                          'imax', '3d', '4k', 'low budget', 'short film'}


def tokens(text):
    text = ''.join(c for c in unicodedata.normalize('NFD', text.casefold()) if not unicodedata.combining(c))
    return Counter(word for word in re.findall(r'[a-z]{3,}', text) if word not in STOPWORDS)


def theme_tokens(names):
    words = Counter(word for name in names if name.casefold().strip() not in NON_NARRATIVE_KEYWORDS
                    for word in tokens(name))
    stems = Counter()
    for word, count in words.items():
        for suffix in ('ingly', 'ation', 'ments', 'ment', 'ness', 'ism', 'ist', 'ing', 'ed', 'es', 's', 'e'):
            if word.endswith(suffix) and len(word) - len(suffix) >= 3:
                word = word[:-len(suffix)]
                break
        if word not in {'film', 'movie', 'thriller', 'horror', 'drama', 'comedy', 'director'}:
            stems[word] += count
    return stems


def keyword_tokens(item):
    return theme_tokens(item.keyword_names.values())


def keyword_importance(item):
    labels = {key: set(theme_tokens([name])) for key, name in item.keyword_names.items()}
    counts = Counter(word for words in labels.values() for word in words)
    maximum = max(counts.values(), default=1)
    return {key: max((counts[word] for word in labels.get(key, ())), default=1) / maximum
            for key in item.keywords if item.keyword_names.get(key, '').casefold().strip() not in NON_NARRATIVE_KEYWORDS}


def cosine(left, right):
    numerator = fsum(left[key] * right.get(key, 0) for key in sorted(left))
    norm = sqrt(fsum(v * v for v in left.values()) * fsum(v * v for v in right.values()))
    return min(1.0, numerator / norm) if norm else 0.0


class RelationEvidence(dict):
    def __init__(self, values=(), *, sources=None):
        super().__init__((key, set(items)) for key, items in dict(values).items())
        self.sources = {key: {source: set(items) for source, items in endpoints.items()}
                        for key, endpoints in (sources or {}).items()}

    def strength(self, seed_key, candidate_key):
        endpoints = self.sources.get(seed_key, {})
        if candidate_key in endpoints.get('recommendations', set()):
            return 1.0
        if candidate_key in endpoints.get('similar', set()):
            return .5
        return float(candidate_key in self.get(seed_key, set()))


class MatchScorer:
    WEIGHTS = {'keyword': .35, 'related': .35, 'genre': .20, 'overview': .08}

    def __init__(self, seeds, candidates, related):
        self.seeds = sorted(seeds, key=lambda item: item.key)
        self.related = related
        documents = {item.key: item for item in [*self.seeds, *candidates]}
        self.words = {key: narrative_terms(item.overview) for key, item in documents.items()}
        self.concepts = {key: thematic_profile(item) for key, item in documents.items()}
        self.keyword_idf = self.idf([item.keywords for item in documents.values()])
        self.keyword_profiles = {key: keyword_importance(item) for key, item in documents.items()}
        self.themes = {key: keyword_tokens(item) for key, item in documents.items()}
        theme_idf = self.idf(self.themes.values())
        self.theme_vectors = {key: {word: count * theme_idf[word] for word, count in words.items()}
                              for key, words in self.themes.items()}
        self.text_idf = self.idf(self.words.values())
        self.vectors = {key: {word: (1 + log(count)) * self.text_idf[word]
                             for word, count in values.items()} for key, values in self.words.items()}
        self.groups = self.cluster()

    @staticmethod
    def idf(documents):
        documents = list(documents)
        counts = Counter(word for values in documents for word in set(values))
        return {word: 1 + log((len(documents) + 1) / (count + 1)) for word, count in counts.items()}

    def keyword_similarity(self, profile, values):
        if not profile or not values:
            return 0.0
        left = {key: value * self.keyword_idf.get(key, 1) for key, value in profile.items()}
        right = {key: self.keyword_idf.get(key, 1) * (values[key] if isinstance(values, dict) else 1)
                 for key in values}
        shared = fsum(min(left[key], right.get(key, 0)) for key in sorted(left))
        shorter = min(fsum(left.values()), fsum(right.values()))
        return .5 * cosine(left, right) + .5 * (shared / shorter if shorter else 0)

    def cluster(self):
        # Complete linkage evita que uma referência intermediária una interesses incompatíveis.
        def connected(a, b):
            shared = len(a.keywords & b.keywords)
            thematic = self.keyword_similarity(self.keyword_profiles[a.key], self.keyword_profiles[b.key])
            named = cosine(self.theme_vectors[a.key], self.theme_vectors[b.key])
            narrative = cosine(self.vectors[a.key], self.vectors[b.key])
            common = set(self.concepts[a.key]) & self.concepts[b.key].keys()
            return ((shared >= 2 and thematic >= .25) or named >= .35
                    or len(common) >= 2
                    or (narrative >= .30 and bool(a.genre_ids() & b.genre_ids())))

        groups = []
        for seed in self.seeds:
            group = next((group for group in groups if all(connected(seed, member) for member in group)), None)
            if group is None:
                groups.append([seed])
            else:
                group.append(seed)
        return groups

    def evaluate_group(self, group, candidate, group_id):
        genres = EvidenceScorer.profile([item.genre_ids() for item in group])
        known = [self.keyword_profiles[item.key] for item in group if item.keywords]
        keywords = {key: fsum(profile.get(key, 0) for profile in known) / len(known)
                    for key in sorted({key for profile in known for key in profile})} if known else {}
        vectors = [self.vectors[item.key] for item in group if len(self.words[item.key]) >= 6]
        narrative = {word: fsum(vector.get(word, 0) for vector in vectors) / len(vectors)
                     for word in sorted({word for vector in vectors for word in vector})} if vectors else {}
        common_keywords = set(keywords) & candidate.keywords
        theme_vectors = [self.theme_vectors[item.key] for item in group if self.theme_vectors[item.key]]
        theme_profile = {word: fsum(vector.get(word, 0) for vector in theme_vectors) / len(theme_vectors)
                         for word in sorted({word for vector in theme_vectors for word in vector})} if theme_vectors else {}
        common_themes = set(theme_profile) & self.themes[candidate.key].keys()
        thematic_tags = min(sum(bool(common_themes & theme_tokens([name]).keys())
                                for name in candidate.keyword_names.values()),
                            max((sum(bool(common_themes & theme_tokens([name]).keys())
                                     for name in seed.keyword_names.values()) for seed in group), default=0))
        keyword = self.keyword_similarity(keywords, self.keyword_profiles[candidate.key])
        if theme_profile and self.theme_vectors[candidate.key]:
            keyword = .5 * keyword + .5 * cosine(theme_profile, self.theme_vectors[candidate.key])
        common_words = set(narrative) & self.words[candidate.key].keys()
        relations = sum(candidate.key in self.related.get(seed.key, set()) for seed in group)
        relation_strength = max((self.related.strength(seed.key, candidate.key)
                                 if isinstance(self.related, RelationEvidence) else
                                 float(candidate.key in self.related.get(seed.key, set())) for seed in group), default=0)
        # Evidências temáticas são fatos compartilhados, não a fração de uma lista de tags incidentais.
        informative_keywords = {key for key in common_keywords if not candidate.keyword_names.get(key)
                                or theme_tokens([candidate.keyword_names[key]])}
        units = max(len(informative_keywords), min(len(common_themes), thematic_tags))
        keyword_overlap = keyword
        keyword = .8 * (units / (units + 1)) + .2 * keyword_overlap if units else 0.0
        concept_counts = Counter(key for seed in group for key in self.concepts[seed.key])
        combined_concepts = {key: count / len(group) for key, count in concept_counts.items()}
        candidate_concepts = self.concepts[candidate.key]
        shared_concepts = set(combined_concepts) & candidate_concepts.keys()
        concept_similarity = self.keyword_similarity(combined_concepts, candidate_concepts)
        if len(shared_concepts) >= 2:
            keyword = .65 * keyword + .35 * concept_similarity
            units = max(units, len(shared_concepts))
        text_cosine = cosine(narrative, self.vectors[candidate.key])
        text_intersection = fsum(min(narrative[word], self.vectors[candidate.key].get(word, 0))
                                 for word in sorted(narrative))
        shorter = min(fsum(narrative.values()), fsum(self.vectors[candidate.key].values()))
        text_coverage = text_intersection / shorter if shorter else 0
        overview = .5 * text_cosine + .5 * text_coverage
        genre_combined = EvidenceScorer.similarity(genres, candidate.genre_ids(), overlap=True)
        genre_individual = max((EvidenceScorer.similarity(dict.fromkeys(seed.genre_ids(), 1),
                                                          candidate.genre_ids(), overlap=True) for seed in group), default=0)
        factors = {
            'genre': .5 * genre_combined + .5 * genre_individual,
            'keyword': keyword,
            'overview': overview,
            'related': relation_strength,
            'rating': max(0, min(1, candidate.rating / 10)) if candidate.rating is not None else 0,
        }
        available = {'genre': bool(genres and candidate.genres), 'keyword': bool(keywords and candidate.keywords),
                     'overview': bool(narrative and len(self.words[candidate.key]) >= 6),
                     'related': bool(relations)}
        weights = dict(self.WEIGHTS)
        text_length = min(len(narrative), len(self.words[candidate.key]))
        weights['overview'] *= min(1, text_length / 20)
        weight = fsum(weights[key] for key in weights if available[key])
        content = fsum(weights[key] * factors[key] for key in weights if available[key]) / weight if weight else 0
        positive = sum((factors['genre'] >= .5, factors['keyword'] >= .45,
                        factors['overview'] >= .35, factors['related'] > 0))
        semantic = units >= 2 or (len(common_words) >= 4 and overview >= .30)
        reliability = 1.0
        if positive < 2 or not semantic:
            reliability = min(reliability, weight)
        known = sum(bool(seed.genres or seed.keywords or seed.overview) for seed in group) / len(group)
        reliability *= known
        value = content * reliability
        score = max(0, min(100, int(100 * value + .5)))
        if not semantic or positive < 2:
            score = min(score, 79)
        related_content = (units >= 1 or not available['keyword']
                           or (overview >= .1 and len(common_words) >= 2))
        relevant = ((relation_strength >= 1 and factors['genre'] >= .5 and related_content)
                    or (relation_strength > 0 and factors['genre'] >= .5 and units >= 2)
                    or (semantic and factors['genre'] >= .5 and (keyword >= .45 or overview >= .30))
                    or (relations > 0 and units >= 3))
        scale = reliability * 100
        factors.update(reliability=reliability, coverage=weight / .98, shared_keywords=len(common_keywords),
                       thematic_units=units, keyword_overlap=keyword_overlap, overview_cosine=text_cosine,
                       relevant_evidence=float(relevant), calibration_version=3.0,
                       concept_similarity=concept_similarity, shared_concepts=len(shared_concepts),
                       shared_themes=len(common_themes),
                       thematic_tags=thematic_tags,
                       shared_words=len(common_words), related_count=relations, group_id=group_id,
                       group_size=len(group), algorithm_version=2.0,
                       **{f'{key}_available': float(value) for key, value in available.items()})
        factors.update({f'{key}_points': scale * weights[key] * factors[key] / weight
                        if weight and available[key] else 0 for key in weights})
        factors.update({f'theme_{key}': 1.0 for key in sorted(shared_concepts)})
        factors['rating_points'] = 0.0
        unrounded = fsum(factors[f'{key}_points'] for key in (*weights, 'rating'))
        capped = min(unrounded, 79) if not semantic or positive < 2 else unrounded
        factors['evidence_cap_points'] = unrounded - capped
        factors['rounding_points'] = score - capped
        return factors, score

    def evaluate(self, candidate):
        evaluations = [self.evaluate_group(group, candidate, index) for index, group in enumerate(self.groups)]
        best = max(evaluations, key=lambda row: (row[1], row[0]['group_size'], -row[0]['group_id']))
        supported = sum((len(set(self.concepts[seed.key]) & self.concepts[candidate.key].keys()) >= 2
                         or len(seed.keywords & candidate.keywords) >= 2) for seed in self.seeds)
        if supported >= 2 and len(self.groups) > 1:
            combined = self.evaluate_group(self.seeds, candidate, best[0]['group_id'])
            coverage = supported / len(self.seeds)
            blended = int(coverage * combined[1] + (1 - coverage) * best[1] + .5)
            if blended > best[1]:
                previous = best[0]
                values = combined[0]
                for key in ('keyword', 'related', 'genre', 'overview', 'rating', 'evidence_cap'):
                    name = f'{key}_points'
                    values[name] = coverage * values[name] + (1 - coverage) * previous[name]
                actual = fsum(values[f'{key}_points'] for key in ('keyword', 'related', 'genre', 'overview', 'rating')) - values['evidence_cap_points']
                blended = int(actual + .5)
                values.update(rounding_points=blended - actual, combined_profile=1.0)
                best = (values, blended)
        best[0].update(reference_count=supported, reference_total=len(self.seeds))
        return best
