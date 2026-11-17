import os
import secrets
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / '.env')


class Config:
    SECRET_KEY = os.getenv('SECRET_KEY') or secrets.token_hex(32)
    DATABASE = str(ROOT / 'instance' / 'cinovelle.sqlite3')
    TMDB_API_KEY = os.getenv('TMDB_API_KEY', '')
    TMDB_READ_ACCESS_TOKEN = os.getenv('TMDB_READ_ACCESS_TOKEN', '')
    OMDB_API_KEY = os.getenv('OMDB_API_KEY', '')
    DEMO_MODE = os.getenv('DEMO_MODE', '').lower() == 'true'
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    MAX_CONTENT_LENGTH = 64 * 1024
