"""Evaluate the requested scenarios against TMDB without exposing credentials or personal data."""
import json
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import create_app
from app.i18n import translate
from app.integrations import IntegrationError


def describe(row):
    reasons = [translate(key, 'pt-BR').format(count=int(row.factors.get(
        'reference_count' if key == 'reason_combined' else 'related_count', 0))) for key in row.explanation_keys]
    topics = [translate(key, 'pt-BR') for key, value in row.factors.items() if key.startswith('theme_') and value]
    return dict(title=row.item.title, media_type=row.item.media_type, score=row.score,
                reasons=reasons, themes=topics, reference_count=row.factors.get('reference_count', 0))


def evaluate():
    with TemporaryDirectory() as folder:
        app = create_app({'DATABASE': str(Path(folder) / 'evaluation.db'), 'DEMO_MODE': False})
        services = app.extensions['cinovelle']; catalog = services['catalog']; engine = services['engine']
        if catalog.demo:
            print('TMDB not configured: real evaluation skipped. Demo remains available.')
            return
        # Evaluation fixtures only; no title IDs are used by the recommendation algorithm.
        ids = {'Get Out':419430, 'Coraline':14836, 'Parasite':496243, 'Interstellar':157336,
               'Arrival':329865, 'Notting Hill':509, 'Toy Story':862}
        references = {name: catalog.get(f'tmdb:movie:{value}', 'pt-BR') for name, value in ids.items()}
        cases = [('A', ['Get Out','Coraline','Parasite']), ('B',['Interstellar','Arrival']),
                 ('C',['Interstellar','Notting Hill','Toy Story'])]
        reports = []
        for label, names in cases:
            print('Evaluating scenario ' + label, flush=True)
            seeds = [references[name] for name in names]
            results = engine.discover(catalog, seeds, 'pt-BR')
            visible = engine.displayable(results)
            row = dict(scenario=label, references=[item.title for item in seeds], evaluated=len(results),
                       relevant=len(visible), top_five=[describe(item) for item in visible[:5]])
            assert [item.score for item in visible] == sorted((item.score for item in visible), reverse=True)
            assert not ({item.key for item in seeds} & {item.item.key for item in visible})
            if label == 'A':
                probe = catalog.get('tmdb:movie:458723', 'pt-BR')
                candidates, related = catalog.candidates(seeds, 'pt-BR')
                audit = engine.recommend(seeds, [*candidates, probe], related)
                checked = next(item for item in audit if item.item.key == probe.key)
                row['evaluation_probe'] = dict(**describe(checked), retrieved=probe.key in {item.key for item in candidates},
                                               relevant=checked.is_relevant)
            reports.append(row)
            print(json.dumps({'scenario':label, 'evaluated':len(results), 'relevant':len(visible)}), flush=True)
        providers = {}
        for key in ('tmdb:movie:419430', 'tmdb:tv:70523'):
            data = catalog.watch_providers(key, 'pt-BR')
            assert catalog.watch_providers(key, 'pt-BR') == data
            providers[key] = dict(region=data['region'], groups=[group['kind'] for group in data['groups']],
                                  official_link=bool(data['link']))
        imdb = {'configured':services['omdb'].configured, 'rating':None}
        if services['omdb'].configured:
            reference = references['Get Out']; catalog.ensure_imdb_id(reference, 'pt-BR')
            imdb['rating'] = services['omdb'].rating(reference.imdb_id)
        output = Path(__file__).resolve().parents[1] / 'artifacts' / 'product-evaluation.json'
        output.parent.mkdir(exist_ok=True)
        output.write_text(json.dumps(dict(scenarios=reports, providers_BR=providers, imdb=imdb),
                                     ensure_ascii=False, indent=2), encoding='utf-8')
        lines = ['# Cinovelle - avaliacao real', '']
        for row in reports:
            lines += ['## ' + row['scenario'] + ': ' + ' + '.join(row['references']), '',
                      '| Titulo | Score | Evidencia |', '|---|---:|---|']
            for result in row['top_five']:
                reasons = ' '.join(result['reasons']) + ' ' + ', '.join(result['themes'])
                lines.append(f"| {result['title']} | {result['score']} | {reasons} |")
            lines.append('')
        output.with_suffix('.md').write_text('\n'.join(lines), encoding='utf-8')
        print(json.dumps({'providers_BR':providers, 'imdb_configured':imdb['configured']}), flush=True)


if __name__ == '__main__':
    try:
        evaluate()
    except IntegrationError as error:
        print('Integration unavailable: ' + error.code, flush=True)
        sys.exit(1)
