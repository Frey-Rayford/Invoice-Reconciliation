import os
from copy import deepcopy
from contextlib import closing
from uuid import uuid4

import pyodbc
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app import storage

pytestmark = pytest.mark.skipif(os.getenv('RUN_SQL_TESTS') != '1', reason='Set RUN_SQL_TESTS=1 to test the configured SQL Server')


def test_real_sql_history_originals_and_rollback():
    client = TestClient(app)
    demo = client.post('/api/demo').json()
    payload = {'po_id': demo['po']['id'], 'invoice_id': demo['invoice']['id'], 'po': demo['po']['document'], 'invoice': demo['invoice']['document'], 'reviewed': True}
    first = client.post('/api/compare', json=payload)
    assert first.status_code == 200, first.text
    first = first.json()
    assert first['result']['net_difference'] == '470000'
    payload['invoice']['lines'][0]['unit_price'] = '150000'
    second = client.post('/api/compare', json=payload)
    assert second.status_code == 200, second.text
    second = second.json()
    assert client.get('/api/runs/' + first['id']).json()['result']['net_difference'] == '470000'
    assert client.get('/api/runs/' + second['id']).json()['result']['net_difference'] == '170000'
    with closing(storage.connection()) as conn:
        count = conn.execute('SELECT COUNT(*) FROM dbo.review_lines WHERE run_id = ?', first['id']).fetchone()[0]
        assert count == 5
        original = conn.execute("SELECT JSON_VALUE(original_json, '$.document.lines[0].unit_price') FROM dbo.documents WHERE document_id = ?", payload['invoice_id']).fetchone()[0]
        assert original == '165000'
    bad = deepcopy(second)
    bad['id'] = str(uuid4())
    bad['snapshot']['invoice']['lines'].append(deepcopy(bad['snapshot']['invoice']['lines'][0]))
    with pytest.raises(pyodbc.Error):
        storage.save_run(bad, [demo['po'], demo['invoice']])
    with closing(storage.connection()) as conn:
        assert conn.execute('SELECT COUNT(*) FROM dbo.review_runs WHERE run_id = ?', bad['id']).fetchone()[0] == 0
        assert conn.execute('SELECT COUNT(*) FROM dbo.review_lines WHERE run_id = ?', bad['id']).fetchone()[0] == 0
