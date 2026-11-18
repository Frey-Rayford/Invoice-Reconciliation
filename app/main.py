import hashlib
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from time import monotonic
from typing import Literal
from uuid import uuid4

import pymupdf as fitz
import pyodbc
from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from openai import OpenAIError
from pydantic import ValidationError

load_dotenv(Path(__file__).resolve().parents[1] / '.env')

from . import storage
from .extract import evidence, extract_ai, extract_template, open_document
from .models import CompareRequest
from .reconcile import reconcile

app = FastAPI(title='Invoice Reconciliation', version='0.1.0')
logger = logging.getLogger(__name__)
STATIC = Path(__file__).resolve().parent / 'static'
app.mount('/static', StaticFiles(directory=STATIC), name='static')


@app.middleware('http')
async def local_write_guard(request: Request, call_next):
    origin = request.headers.get('origin')
    if request.method not in ('GET', 'HEAD', 'OPTIONS') and origin:
        if origin != str(request.base_url).rstrip('/'):
            return Response('Origin not allowed', status_code=403)
    response = await call_next(request)
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Cache-Control'] = 'no-store'
    return response


@app.get('/')
def index():
    return FileResponse(STATIC / 'index.html')


@app.get('/api/status')
def status():
    return {'sql_connected': storage.sql_status(),
            'ai_configured': bool(os.getenv('OPENAI_API_KEY') and os.getenv('OPENAI_MODEL'))}


def ingest(raw, filename, kind, method):
    if len(raw) > 10 * 1024 * 1024:
        raise ValueError('Tài liệu vượt giới hạn 10 MB.')
    started = monotonic()
    with open_document(raw, filename) as pdf:
        document, usage = (extract_ai if method == 'ai' else extract_template)(pdf, kind)
        identifier = str(uuid4())
        normalized = pdf.tobytes(garbage=4, deflate=True)
        payload = {
            'id': identifier, 'filename': Path(filename.replace('\\', '/')).name[:250],
            'sha256': hashlib.sha256(raw).hexdigest(), 'method': method,
            'document': document.model_dump(mode='json'), 'evidence': evidence(pdf, document),
            'pages': len(pdf), 'usage': usage, 'seconds': round(monotonic()-started, 2),
            'created_at': datetime.now(timezone.utc).isoformat(),
        }
        storage.path_for(identifier, '.pdf').write_bytes(normalized)
        storage.write_json(storage.path_for(identifier, '.json'), payload)
    return payload


@app.post('/api/documents')
def upload(file: UploadFile = File(...), kind: Literal['PO', 'INVOICE'] = Form(...), method: Literal['template', 'ai'] = Form(...)):
    raw = file.file.read(10 * 1024 * 1024 + 1)
    try:
        return ingest(raw, file.filename or 'document.pdf', kind, method)
    except (ValueError, ValidationError) as exc:
        raise HTTPException(422, str(exc)) from exc
    except OpenAIError as exc:
        logger.warning('AI request failed: %s', type(exc).__name__)
        raise HTTPException(502, 'Không nhận được kết quả AI. Kiểm tra model, API key hoặc hạn mức; bản mẫu vẫn dùng được.') from exc


@app.post('/api/demo')
def demo():
    samples = storage.ROOT / 'samples'
    return {kind.lower(): ingest((samples / name).read_bytes(), name, kind, 'template')
            for kind, name in [('PO', 'purchase-order.pdf'), ('INVOICE', 'invoice.pdf')]}


@app.get('/api/samples/{name}')
def sample(name: Literal['purchase-order.pdf', 'invoice.pdf']):
    return FileResponse(storage.ROOT / 'samples' / name, filename=name)


def stored(identifier):
    try:
        return storage.load_document(identifier)
    except (ValueError, FileNotFoundError) as exc:
        raise HTTPException(404, 'Không tìm thấy chứng từ.') from exc


@app.get('/api/documents/{identifier}')
def document_metadata(identifier: str):
    return stored(identifier)


@app.get('/api/documents/{identifier}/page/{page_number}')
def page_image(identifier: str, page_number: int):
    metadata = stored(identifier)
    if not 1 <= page_number <= metadata['pages']:
        raise HTTPException(404, 'Không có trang này.')
    with fitz.open(storage.path_for(identifier, '.pdf')) as pdf:
        page = pdf[page_number-1]
        scale = min(1.5, 1500 / max(page.rect.width, page.rect.height))
        return Response(page.get_pixmap(matrix=fitz.Matrix(scale, scale)).tobytes('png'), media_type='image/png')


@app.post('/api/compare')
def compare(request: CompareRequest):
    if not request.reviewed:
        raise HTTPException(422, 'Kiểm tra dữ liệu và đánh dấu xác nhận trước khi đối chiếu.')
    po, inv = stored(request.po_id), stored(request.invoice_id)
    if po['document']['kind'] != 'PO' or inv['document']['kind'] != 'INVOICE':
        raise HTTPException(422, 'Loại tài liệu nguồn không khớp.')
    try:
        result = reconcile(request.po, request.invoice)
        for metadata, doc in [(po, request.po), (inv, request.invoice)]:
            if any(line.page > metadata['pages'] for line in doc.lines):
                raise ValueError('Số trang vượt quá tài liệu nguồn.')
        run = {'id': str(uuid4()), 'snapshot': request.model_dump(mode='json'), 'result': result}
        storage.save_run(run, [po, inv])
        run['saved'] = True
        return run
    except (ValueError, ValidationError) as exc:
        raise HTTPException(422, str(exc)) from exc
    except pyodbc.Error as exc:
        logger.warning('Database save failed: %s', type(exc).__name__)
        raise HTTPException(503, 'Chưa lưu được vào SQL Server. Dữ liệu đang sửa vẫn còn trên màn hình; bật dịch vụ và thử lại.') from exc


@app.get('/api/runs')
def runs():
    try:
        return storage.history()
    except (pyodbc.Error, ValueError) as exc:
        raise HTTPException(503, 'SQL Server chưa sẵn sàng.') from exc


@app.get('/api/runs/{identifier}')
def run(identifier: str):
    try:
        return storage.get_run(identifier)
    except (ValueError, FileNotFoundError) as exc:
        raise HTTPException(404, 'Không tìm thấy lần đối chiếu.') from exc
    except pyodbc.Error as exc:
        raise HTTPException(503, 'SQL Server chưa sẵn sàng.') from exc
