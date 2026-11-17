"""Verifica o artefato extraído em processo independente, usando banco temporário."""
import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
from zipfile import ZipFile

from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]


def verify():
    archive_path = ROOT / 'cinovelle-projeto-poo.zip'
    with TemporaryDirectory(prefix='cinovelle-check-') as directory:
        with ZipFile(archive_path) as archive:
            assert archive.testzip() is None
            names = archive.namelist()
            required = ['run.py', '.env.example', 'requirements.txt', 'requirements-lock.txt', 'package.json',
                        'package-lock.json', 'README.md', 'app/services/match.py', 'app/services/themes.py',
                        'app/templates/watchlist.html', 'tests/search-selection.test.js']
            assert all(f'cinovelle/{name}' in names for name in required), 'Arquivo necessario ausente no ZIP'
            forbidden = {'.env', '.venv', 'venv', '.git', 'node_modules', '__pycache__', '.pytest_cache', 'instance', 'artifacts'}
            assert all(name.startswith('cinovelle/') and '..' not in Path(name).parts
                       and not (set(Path(name).parts) & forbidden)
                       and not name.endswith(('.pyc', '.sqlite3', '.db', '.pem', '.key')) for name in names), 'Arquivo indevido no ZIP'
            assert len(names) == len(set(names)), 'Entradas duplicadas no ZIP'
            # Compara valores sem imprimir ou distribuir as credenciais locais.
            local = dotenv_values(ROOT / '.env')
            example = dotenv_values(ROOT / '.env.example')
            secrets = [value.encode() for key, value in local.items()
                       if key in {'SECRET_KEY', 'TMDB_API_KEY', 'TMDB_READ_ACCESS_TOKEN', 'OMDB_API_KEY'}
                       and value and len(value) >= 8 and value != example.get(key)]
            assert not any(secret in archive.read(name) for secret in secrets for name in names), 'Credencial local encontrada no ZIP'
            assert all((ROOT / Path(name).relative_to('cinovelle')).read_bytes() == archive.read(name)
                       for name in names), 'ZIP desatualizado em relacao aos arquivos locais'
            archive.extractall(directory)
        checkout = Path(directory) / 'cinovelle'
        # O processo importa exclusivamente a aplicação extraída, sem reutilizar módulos carregados.
        program = '''
import json
from pathlib import Path
from app import create_app
app = create_app({'TESTING':True,'SECRET_KEY':'delivery-test','DATABASE':str(Path.cwd()/'test.db'),
                  'DEMO_MODE':True,'TMDB_API_KEY':'','TMDB_READ_ACCESS_TOKEN':'','OMDB_API_KEY':''})
with app.test_client() as client:
    assert client.get('/').status_code == 200
    assert client.get('/title/demo:movie:1').status_code == 200
    with client.session_transaction() as state:
        token = state['csrf_token']
    assert client.post('/profiles', data={'name':'Entrega','csrf_token':token}).status_code == 302
    assert client.get('/api/search?q=orbita').json['items']
    assert client.post('/taste', data={'name':'Entrega revisada','genres':'18','csrf_token':token}).status_code == 302
    assert client.post('/selection', data={'key':'demo:movie:1','csrf_token':token}).status_code == 302
    assert client.post('/recommendations', data={'csrf_token':token}).status_code == 200
    assert client.get('/taste').status_code == 200
    assert client.post('/favorites', data={'key':'demo:movie:1','csrf_token':token}).status_code == 302
    assert client.post('/watchlist', data={'key':'demo:tv:3','csrf_token':token}).status_code == 302
    assert len(app.extensions['cinovelle']['watchlist'].list(1)) == 1
    assert client.get('/watchlist').status_code == 200
    assert client.get('/api/title/demo:movie:1/providers').json['groups'] == []
    assert len(app.extensions['cinovelle']['favorites'].list(1)) == 1
    assert client.get('/favorites').status_code == 200
    assert client.post('/favorites', data={'key':'demo:movie:1','action':'remove','csrf_token':token}).status_code == 302
    assert app.extensions['cinovelle']['favorites'].list(1) == []
    assert client.post('/history/delete', data={'csrf_token':token}).status_code == 302
    assert app.extensions['cinovelle']['history'].list(1) == []
    similar=client.post('/similar/demo:movie:9', data={'csrf_token':token})
    assert similar.status_code == 200 and similar.text.count('id="recommend-form"') == 1
    assert client.post('/logout', data={'csrf_token':token}).status_code == 302
    assert client.post('/profiles/1/enter', data={'csrf_token':token}).status_code == 302
    assert client.post('/profiles/1/delete', data={'csrf_token':token}).status_code == 302
    assert app.extensions['cinovelle']['profiles'].all() == []
with app.extensions['cinovelle']['db'].connection() as connection:
    assert connection.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
    assert connection.execute('PRAGMA foreign_key_check').fetchall() == []
    tables=connection.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'").fetchall()
    assert len(tables) == 8
print(json.dumps({'archive':'OK','demo_crud':'OK','search':'OK','recommendations':'OK','history':'OK','login_logout':'OK','sqlite_tables':len(tables)}))
'''
        result = subprocess.run([sys.executable, '-c', program], cwd=checkout, capture_output=True, text=True, check=True)
        print(json.loads(result.stdout))


if __name__ == '__main__':
    verify()
