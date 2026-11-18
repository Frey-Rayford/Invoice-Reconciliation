from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pymupdf as fitz
import pytest

from app import extract
from app.reconcile import reconcile

SAMPLES = Path(__file__).resolve().parents[1] / 'samples'


def test_sample_extraction_amounts_and_evidence():
    with fitz.open(SAMPLES / 'purchase-order.pdf') as pdf:
        po, _ = extract.extract_template(pdf, 'PO')
        anchors = extract.evidence(pdf, po)
        assert all(a['text_found'] for a in anchors.values())
        assert all(0 <= n <= 1 for a in anchors.values() for rect in a['rects'] for n in rect)
    with fitz.open(SAMPLES / 'invoice.pdf') as pdf:
        invoice, _ = extract.extract_template(pdf, 'INVOICE')
    result = reconcile(po, invoice)
    assert result['net_difference'] == '470000'
    assert result['po_total'] == '3250000'
    assert result['invoice_total'] == '3720000'
    assert result['counts'] == {'difference': 3}


@pytest.mark.parametrize('name', ['bad.pdf', 'bad.exe', 'bad.png'])
def test_bad_files_rejected(name):
    with pytest.raises(ValueError):
        extract.open_document(b'not a document', name)


def test_template_rejects_other_documents_and_wrong_kind():
    with fitz.open() as pdf:
        pdf.new_page()
        with pytest.raises(ValueError):
            extract.extract_template(pdf, 'PO')
    with fitz.open(SAMPLES / 'invoice.pdf') as pdf:
        with pytest.raises(ValueError):
            extract.extract_template(pdf, 'PO')


def test_ai_requires_configuration(monkeypatch):
    monkeypatch.delenv('OPENAI_API_KEY', raising=False)
    with fitz.open(SAMPLES / 'invoice.pdf') as pdf, pytest.raises(ValueError):
        extract.extract_ai(pdf, 'INVOICE')


@pytest.mark.parametrize('scenario', ['valid', 'refusal', 'incomplete', 'wrong_kind', 'wrong_page', 'bad_number'])
def test_ai_adapter_validates_provider_output(monkeypatch, scenario):
    monkeypatch.setenv('OPENAI_API_KEY', 'test-only')
    monkeypatch.setenv('OPENAI_MODEL', 'test-model')
    parsed = extract.ExtractedDocument(kind='INVOICE', number='I-1', po_reference='P-1', supplier='Demo', currency='VND', lines=[
        extract.ExtractedLine(sku='A', description='Paper', unit='box', quantity='2', unit_price='100', stated_total='200', page=1, quote='Paper')])
    if scenario == 'wrong_kind': parsed.kind = 'PO'
    if scenario == 'wrong_page': parsed.lines[0].page = 2
    if scenario == 'bad_number': parsed.lines[0].quantity = 'NaN'
    response = SimpleNamespace(status='incomplete' if scenario == 'incomplete' else 'completed', output_parsed=None if scenario == 'refusal' else parsed, usage=None)
    client = Mock()
    client.responses.parse.return_value = response
    constructor = Mock(return_value=client)
    monkeypatch.setattr(extract, 'OpenAI', constructor)
    with fitz.open(SAMPLES / 'invoice.pdf') as pdf:
        if scenario == 'valid':
            doc, usage = extract.extract_ai(pdf, 'INVOICE')
            assert doc.lines[0].line_id == '1'
            assert usage['model'] == 'test-model'
        else:
            with pytest.raises(ValueError): extract.extract_ai(pdf, 'INVOICE')
    assert constructor.call_args.kwargs['max_retries'] == 0
    assert client.responses.parse.call_args.kwargs['store'] is False
