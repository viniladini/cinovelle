import pytest

from app import create_app


@pytest.fixture
def app(tmp_path):
    return create_app({'TESTING': True, 'SECRET_KEY': 'test-key', 'DATABASE': str(tmp_path / 'test.db'),
                       'DEMO_MODE': True, 'TMDB_API_KEY': '', 'TMDB_READ_ACCESS_TOKEN': '', 'OMDB_API_KEY': ''})


@pytest.fixture
def services(app):
    return app.extensions['cinovelle']


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def post(client):
    client.get('/')
    with client.session_transaction() as session:
        token = session['csrf_token']

    def send(path, data=None, **kwargs):
        return client.post(path, data={**(data or {}), 'csrf_token': token}, **kwargs)
    return send
