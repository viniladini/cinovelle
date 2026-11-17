import importlib.util
from pathlib import Path
from zipfile import ZipFile


def test_zip_contains_app_without_runtime_data(tmp_path, monkeypatch):
    script = Path(__file__).resolve().parents[1] / 'scripts' / 'package.py'
    spec = importlib.util.spec_from_file_location('cinovelle_package', script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    output = tmp_path / 'release.zip'
    monkeypatch.setattr(module, 'OUTPUT', output)
    module.package()
    with ZipFile(output) as archive:
        names = archive.namelist()
        assert archive.testzip() is None
        assert 'cinovelle/run.py' in names
        assert 'cinovelle/.env.example' in names
        assert 'cinovelle/app/static/tmdb.svg' in names
        assert 'cinovelle/package.json' in names
        assert 'cinovelle/package-lock.json' in names
        assert 'cinovelle/tests/search-selection.test.js' in names
        assert 'cinovelle/app/services/match.py' in names
        assert 'cinovelle/app/services/themes.py' in names
        assert 'cinovelle/app/templates/watchlist.html' in names
        assert 'cinovelle/SEMINARIO.md' not in names
        assert 'cinovelle/CHECKLIST_ENTREGA.md' not in names
        assert all(not any(part in {'.venv','.git','instance','__pycache__','.pytest_cache','node_modules','artifacts'}
                           for part in Path(name).parts) for name in names)
        assert all(not name.endswith(('.sqlite3','.db','.pyc','/.env')) for name in names)
