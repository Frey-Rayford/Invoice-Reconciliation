import json
import os
from contextlib import closing
from pathlib import Path
from uuid import UUID

import pyodbc

ROOT = Path(__file__).resolve().parents[1]
DATA = Path(os.getenv('RECONCILE_DATA_DIR', str(ROOT / 'data')))


def folder():
    DATA.mkdir(parents=True, exist_ok=True)
    return DATA


def path_for(identifier, suffix):
    return folder() / (str(UUID(identifier)) + suffix)


def write_json(path, payload):
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
    temporary.replace(path)


def load_document(identifier):
    return json.loads(path_for(identifier, '.json').read_text(encoding='utf-8'))


def connection():
    value = os.getenv('SQL_CONNECTION_STRING')
    if not value:
        raise ValueError('SQL_CONNECTION_STRING chưa được cấu hình.')
    return pyodbc.connect(value, timeout=3)


def sql_status():
    try:
        with closing(connection()) as conn:
            return conn.execute("SELECT COUNT(*) FROM dbo.review_runs").fetchone() is not None
    except (pyodbc.Error, ValueError):
        return False


def save_run(run, documents):
    with closing(connection()) as conn:
        try:
            cursor = conn.cursor()
            for document in documents:
                cursor.execute('''IF NOT EXISTS (SELECT 1 FROM dbo.documents WHERE document_id = ?)
                    INSERT INTO dbo.documents
                    (document_id, kind, filename, sha256, extraction_method, original_json)
                    VALUES (?, ?, ?, ?, ?, ?)''',
                    document['id'], document['id'], document['document']['kind'], document['filename'],
                    document['sha256'], document['method'], json.dumps(document, ensure_ascii=False))
            result, snapshot = run['result'], run['snapshot']
            cursor.execute('''INSERT INTO dbo.review_runs
                (run_id, po_id, invoice_id, currency, net_difference, reviewed, complete, snapshot_json, result_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                run['id'], snapshot['po_id'], snapshot['invoice_id'], result['currency'],
                result['net_difference'], snapshot['reviewed'], result['complete'],
                json.dumps(snapshot, ensure_ascii=False), json.dumps(result, ensure_ascii=False))
            for kind in ('po', 'invoice'):
                for line in snapshot[kind]['lines']:
                    cursor.execute('''INSERT INTO dbo.review_lines
                        (run_id, document_kind, line_id, sku, description, unit, quantity, unit_price,
                         stated_total, source_page, source_quote) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                        run['id'], snapshot[kind]['kind'], line['line_id'], line['sku'], line['description'],
                        line['unit'], line['quantity'], line['unit_price'], line['stated_total'], line['page'], line['quote'])
            conn.commit()
        except Exception:
            conn.rollback()
            raise


def history():
    with closing(connection()) as conn:
        rows = conn.execute('''SELECT TOP (30) CONVERT(varchar(36), run_id), currency,
            net_difference, complete, created_at FROM dbo.review_runs ORDER BY created_at DESC''').fetchall()
        return [{'id': r[0], 'currency': r[1], 'delta': str(r[2]) if r[2] is not None else None,
                 'complete': bool(r[3]), 'created_at': r[4].isoformat() + 'Z'} for r in rows]


def get_run(identifier):
    identifier = str(UUID(identifier))
    with closing(connection()) as conn:
        row = conn.execute('SELECT snapshot_json, result_json FROM dbo.review_runs WHERE run_id = ?', identifier).fetchone()
        if row is None:
            raise FileNotFoundError(identifier)
        return {'id': identifier, 'snapshot': json.loads(row[0]), 'result': json.loads(row[1]), 'saved': True}
