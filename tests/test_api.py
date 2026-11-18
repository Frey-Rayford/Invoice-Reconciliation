from copy import deepcopy

import pyodbc
import pytest
from fastapi.testclient import TestClient

from app import storage
from app.main import app


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, 'DATA', tmp_path)
    return TestClient(app)


def request_for(client):
    response = client.post('/api/demo')
    assert response.status_code == 200
    demo = response.json()
    return {'po_id': demo['po']['id'], 'invoice_id': demo['invoice']['id'], 'po': demo['po']['document'], 'invoice': demo['invoice']['document'], 'reviewed': True}


def test_review_and_snapshot_persistence(client, monkeypatch):
    saved = []
    monkeypatch.setattr(storage, 'save_run', lambda run, docs: saved.append(deepcopy((run, docs))))
    payload = request_for(client)
    response = client.post('/api/compare', json=payload)
    assert response.status_code == 200
    assert response.json()['result']['net_difference'] == '470000'
    payload['invoice']['lines'][0]['unit_price'] = '150000'
    response = client.post('/api/compare', json=payload)
    assert response.json()['result']['net_difference'] == '170000'
    assert saved[1][0]['snapshot']['invoice']['lines'][0]['unit_price'] == '150000'
    assert saved[1][1][1]['document']['lines'][0]['unit_price'] == '165000'


def test_review_confirmation_required(client, monkeypatch):
    monkeypatch.setattr(storage, 'save_run', lambda *_: pytest.fail('Should not save'))
    payload = request_for(client)
    payload['reviewed'] = False
    assert client.post('/api/compare', json=payload).status_code == 422


def test_sql_error_is_not_reported_as_success(client, monkeypatch):
    def fail(*_): raise pyodbc.OperationalError('offline')
    monkeypatch.setattr(storage, 'save_run', fail)
    response = client.post('/api/compare', json=request_for(client))
    assert response.status_code == 503
    assert 'saved' not in response.json()


def test_source_page_limits(client):
    payload = request_for(client)
    path = '/api/documents/' + payload['po_id']
    assert client.get(path + '/page/1').headers['content-type'] == 'image/png'
    assert client.get(path + '/page/2').status_code == 404
    payload['po']['lines'][0]['page'] = 2
    assert client.post('/api/compare', json=payload).status_code == 422


def test_invalid_upload(client):
    response = client.post('/api/documents', data={'kind': 'PO', 'method': 'template'}, files={'file': ('bad.pdf', b'broken', 'application/pdf')})
    assert response.status_code == 422


def test_cross_origin_write_rejected(client):
    assert client.post('/api/demo', headers={'Origin': 'https://unrelated.example'}).status_code == 403
