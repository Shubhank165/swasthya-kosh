from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

from medikiosk.app import create_app
from medikiosk.config import Settings
from medikiosk.storage import EncryptedSessionStore


def test_full_report_and_correction_survive_backend_restart(tmp_path):
    key = Fernet.generate_key().decode()
    path = tmp_path / 'sessions.db'
    settings = Settings(deployment_profile='demo', session_store_path=path,
                        session_encryption_key=key)
    store = EncryptedSessionStore(path, key)
    store.save_report('synthetic-visit', {'clinical': {'complaint': 'synthetic complaint'}})
    with TestClient(create_app(settings)) as client:
        response = client.get('/api/encounters/synthetic-visit')
        assert response.json()['report']['clinical']['complaint'] == 'synthetic complaint'
        response = client.post('/api/encounters/synthetic-visit/correct',
                               json={'key': 'age_years', 'value': 42, 'by': 'test clinician'})
        assert response.json()['ok']
    with TestClient(create_app(settings)) as restarted:
        report = restarted.get('/api/encounters/synthetic-visit').json()['report']
        assert report['provenance']['entries'][0]['value'] == 42
    assert b'synthetic complaint' not in path.read_bytes()
    assert b'test clinician' not in path.read_bytes()
