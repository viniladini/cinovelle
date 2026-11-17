"""Vocabulário local PT/EN: só reconhece conceitos explicitamente presentes nos metadados."""
import re
import unicodedata
from collections import Counter


VOCABULARY = {
    'psychological': ('psychological thriller', 'psychological horror', 'psychological manipulation', 'mind games', 'suspense psicologico', 'terror psicologico', 'manipulacao psicologica', 'jogos mentais'),
    'family': ('family', 'family relationships', 'parents', 'parents-in-law', 'father daughter', 'mother daughter', 'father son', 'familia', 'familiares', 'pai', 'mae', 'filha', 'filho'),
    'mystery': ('mystery', 'dark secret', 'secrets', 'secret', 'misterio', 'segredo', 'segredos'),
    'identity': ('identity', 'doppelganger', 'duality', 'body swap', 'identidade', 'duplo', 'sosia', 'troca de corpos'),
    'investigation': ('investigation', 'detective', 'investigacao', 'investiga', 'investigar', 'detetive'),
    'survival': ('survival', 'survive', 'survival situation', 'sobrevivencia', 'sobreviver', 'sobreviventes'),
    'social': ('social commentary', 'social criticism', 'social injustice', 'class differences', 'working class', 'capitalism', 'anti-capitalist', 'racism', 'racist', 'race-conscious', 'critica social', 'desigualdade', 'classe social', 'racismo', 'pobreza'),
    'supernatural': ('supernatural', 'ghost', 'haunted', 'possession', 'sobrenatural', 'fantasma', 'assombrada', 'assombrado', 'possessao'),
    'deception': ('manipulation', 'deception', 'con artist', 'scam artist', 'infiltration', 'conspiracy', 'manipulacao', 'engano', 'infiltracao', 'conspiracao', 'golpe'),
    'isolation': ('isolation', 'seclusion', 'confinement', 'isolamento', 'isolada', 'isolado', 'confinamento'),
    'space': ('space', 'spacecraft', 'space travel', 'space station', 'astronaut', 'wormhole', 'espaco', 'espacial', 'astronauta', 'buraco de minhoca'),
    'time': ('time travel', 'time warp', 'time-manipulation', 'viagem no tempo', 'viagem temporal', 'tempo'),
    'communication': ('communication', 'language barrier', 'linguist', 'comunicacao', 'linguista', 'linguagem', 'transmissao'),
    'science': ('science', 'scientist', 'quantum mechanics', 'scientific', 'ciencia', 'cientista', 'cientifica', 'cientifico'),
    'alien': ('alien', 'extraterrestrial', 'extraterrestre', 'extraterrestres', 'first contact', 'primeiro contato'),
    'memory': ('memory', 'memory loss', 'amnesia', 'memoria', 'memorias', 'amnésia'),
    'journey': ('journey', 'expedition', 'adventure', 'jornada', 'expedicao', 'aventura', 'viagem'),
    'romance': ('romance', 'romantic', 'love story', 'romantico', 'romantica', 'amor'),
    'nature': ('nature', 'forest', 'garden', 'natureza', 'floresta', 'jardim'),
}


def normalize(text):
    return ''.join(c for c in unicodedata.normalize('NFD', text.casefold()) if not unicodedata.combining(c))


PATTERNS = {key: [re.compile(r'(?<!\w)' + re.escape(normalize(phrase)) + r'(?!\w)') for phrase in phrases]
            for key, phrases in VOCABULARY.items()}


def concepts(text):
    text = normalize(text)
    return {key for key, patterns in PATTERNS.items() if any(pattern.search(text) for pattern in patterns)}


def profile(item):
    labels = ' '.join(item.keyword_names.values())
    if item.source == 'demo':
        labels += ' ' + ' '.join(item.keywords)
    values = {key: .7 for key in concepts(item.overview)}
    values.update({key: 1.0 for key in concepts(labels)})
    return values


def narrative_terms(text):
    normalized = normalize(text)
    words = re.findall(r'[a-z]{3,}', normalized)
    pt = sum(word in {'uma', 'que', 'com', 'para', 'seus', 'sua', 'nao', 'dos', 'das', 'pela'} for word in words)
    en = sum(word in {'the', 'and', 'with', 'their', 'her', 'his', 'from', 'who', 'when', 'into'} for word in words)
    language = 'pt' if pt > en else 'en' if en > pt else 'und'
    stop = set('the and for that with from this are was were has have had his her their they them into when who what which while about after before through over under out will can not but its she him you your our one two more most some than then there where being been upon must uma umas uns um de da do das dos em no na nos nas que com por para como aos seu sua seus suas ele ela eles elas ser sao foi eram era tem ter pelo pela entre mais quando onde sobre ate apos antes durante enquanto'.split())
    return Counter({f'{language}:{word}': count for word, count in Counter(words).items() if word not in stop})
