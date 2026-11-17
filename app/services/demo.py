from app.models import Genre, Movie, TVSeries

# Catálogo autoral fictício: nenhuma avaliação é atribuída a obras reais.
GENRES = {
    18: ('Drama', 'Drama'), 10749: ('Romance', 'Romance'), 878: ('Ficção científica', 'Science fiction'),
    9648: ('Mistério', 'Mystery'), 35: ('Comédia', 'Comedy'), 12: ('Aventura', 'Adventure'),
    16: ('Animação', 'Animation'), 53: ('Suspense', 'Thriller'),
}
ROWS = [
 ('movie','Depois da última sessão','After the Last Screening',2024,[18,10749],['cinema','memória','reencontro'],'Uma projecionista encontra cartas esquecidas no último cinema de uma cidade litorânea.','A projectionist finds forgotten letters in the last cinema of a seaside town.'),
 ('movie','O mapa do silêncio','A Map of Silence',2023,[18,9648],['memória','cidade','segredo'],'Um cartógrafo refaz o caminho de uma mulher que desapareceu dos mapas.','A cartographer retraces the steps of a woman who disappeared from the maps.'),
 ('tv','Órbita distante','Distant Orbit',2025,[878,9648],['espaço','tempo','segredo'],'Uma transmissão chega a uma estação espacial vinte anos antes de ser enviada.','A transmission reaches a space station twenty years before it was sent.'),
 ('movie','Jardins de novembro','November Gardens',2022,[18,10749],['reencontro','família','memória'],'Dois desconhecidos dividem a tarefa de restaurar um jardim e uma história.','Two strangers share the task of restoring a garden and a story.'),
 ('tv','As horas azuis','The Blue Hours',2024,[18,10749],['cidade','reencontro','cinema'],'Na madrugada de uma metrópole, cinco vidas se cruzam em um café.','Five lives intersect in an all-night café.'),
 ('movie','Entre duas luas','Between Two Moons',2025,[878,18],['espaço','memória','tempo'],'Uma botânica retorna à Terra e descobre que ninguém se lembra dela.','A botanist returns to Earth to discover nobody remembers her.'),
 ('tv','Arquivo das marés','The Tide Archive',2023,[9648,53],['segredo','cidade','memória'],'Uma arquivista investiga fotografias de uma cidade que ainda não foi construída.','An archivist investigates photographs of a city yet to be built.'),
 ('movie','Um verão em Saturno','A Summer on Saturn',2021,[878,35,10749],['espaço','reencontro','viagem'],'Dois viajantes perdem a última nave de volta para casa.','Two travellers miss the last ship home.'),
 ('movie','A casa de papel azul','The Blue Paper House',2024,[16,12],['família','viagem','natureza'],'Uma menina constrói uma casa que aprende a caminhar.','A girl builds a house that learns to walk.'),
 ('tv','Pequenos desastres','Small Disasters',2025,[35,18],['família','cidade','reencontro'],'Três irmãos herdam uma floricultura e uma longa lista de dívidas.','Three siblings inherit a flower shop and a long list of debts.'),
 ('movie','A floresta dos relógios','The Clock Forest',2020,[16,12,9648],['tempo','natureza','segredo'],'Um aprendiz de relojoeiro procura a hora perdida em uma floresta.','An apprentice clockmaker searches a forest for a missing hour.'),
 ('tv','Horizonte zero','Zero Horizon',2024,[878,12],['espaço','viagem','tempo'],'Uma tripulação segue uma constelação que se move contra o tempo.','A crew follows a constellation moving against time.'),
 ('movie','O último apartamento','The Last Apartment',2023,[53,9648],['cidade','segredo','tempo'],'Uma inquilina escuta amanhã através da parede.','A tenant hears tomorrow through the wall.'),
 ('tv','Cartas do interior','Letters from Home',2022,[18,10749],['família','memória','reencontro'],'Uma carteira entrega correspondências que ficaram trinta anos esquecidas.','A postal worker delivers letters forgotten for thirty years.'),
 ('movie','Manual para desaparecer','How to Disappear',2025,[35,12],['viagem','cidade','reencontro'],'Um mágico fracassado parte em busca de seu assistente invisível.','An unsuccessful magician sets out to find his invisible assistant.'),
 ('tv','O jardim das máquinas','The Machine Garden',2024,[878,18,9648],['natureza','memória','segredo'],'Uma técnica descobre plantas crescendo dentro de máquinas abandonadas.','A technician discovers plants growing inside abandoned machines.'),
 ('movie','Antes do amanhecer vermelho','Before the Red Dawn',2021,[53,18],['família','segredo','cidade'],'Uma jornalista precisa escolher quais histórias merecem ser contadas.','A journalist must decide which stories deserve to be told.'),
 ('tv','A ilha que sonhava','The Dreaming Island',2025,[16,12],['natureza','família','viagem'],'Uma ilha flutuante e seus habitantes procuram um lugar no oceano.','A floating island and its inhabitants search for a place in the ocean.'),
]


def demo_catalog(language='pt-BR'):
    en = language == 'en-US'
    items = []
    for index, (kind, pt, title, year, genres, keywords, synopsis, english) in enumerate(ROWS, 1):
        cls = Movie if kind == 'movie' else TVSeries
        items.append(cls(index, title if en else pt, str(year), english if en else synopsis,
                         [Genre(g, GENRES[g][en]) for g in genres], set(keywords),
                         poster=f'/static/posters/{index}.svg', runtime=100 + index if kind == 'movie' else None,
                         seasons=1 + index % 3 if kind == 'tv' else None))
    return items
