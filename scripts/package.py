"""Empacota somente fontes revisáveis; nunca inclui dados locais ou segredos."""
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / 'cinovelle-projeto-poo.zip'
DIRECTORIES = ('app', 'tests', 'scripts')
FILES = ('run.py', 'requirements.txt', 'requirements-lock.txt', '.env.example', '.gitignore',
         'README.md', 'pytest.ini', 'package.json', 'package-lock.json')
SUFFIXES = {'.py', '.html', '.css', '.js', '.svg'}


def package():
    paths = [ROOT / name for name in FILES]
    for name in DIRECTORIES:
        paths.extend(path for path in (ROOT / name).rglob('*')
                     if path.is_file() and path.suffix in SUFFIXES
                     and not any(part.startswith('.') or part == '__pycache__' for part in path.relative_to(ROOT).parts))
    missing = [path.name for path in paths if not path.is_file()]
    if missing:
        raise FileNotFoundError(', '.join(missing))
    with ZipFile(OUTPUT, 'w', ZIP_DEFLATED) as archive:
        for path in sorted(paths):
            archive.write(path, f'cinovelle/{path.relative_to(ROOT).as_posix()}')
    with ZipFile(OUTPUT) as archive:
        if archive.testzip():
            raise RuntimeError('Falha na verificação de integridade do ZIP.')
    print(f'{OUTPUT.name}: {len(paths)} arquivos; {OUTPUT.stat().st_size:,} bytes.')


if __name__ == '__main__':
    package()
