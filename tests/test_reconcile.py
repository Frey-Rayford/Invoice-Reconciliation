from copy import deepcopy
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.models import Document, Line
from app.reconcile import reconcile


def pair():
    line = Line(line_id='1', sku='A', description='Paper', unit='box', quantity='2', unit_price='100')
    po = Document(kind='PO', number='PO-1', supplier='Stationery', currency='VND', lines=[line])
    invoice = Document(kind='INVOICE', number='INV-1', po_reference='PO-1', supplier='Stationery', currency='VND', lines=[deepcopy(line)])
    return po, invoice


def test_matched():
    result = reconcile(*pair())
    assert result['counts'] == {'matched': 1}
    assert result['net_difference'] == '0'


def test_quantity_and_price_change_use_full_line_amount():
    po, invoice = pair()
    invoice.lines[0].quantity = Decimal('3')
    invoice.lines[0].unit_price = Decimal('110')
    result = reconcile(po, invoice)
    assert result['net_difference'] == '130'
    assert result['counts'] == {'difference': 1}
    assert len(result['rows'][0]['notes']) == 2


def test_equal_totals_do_not_hide_differences():
    po, invoice = pair()
    invoice.lines[0].quantity = Decimal('4')
    invoice.lines[0].unit_price = Decimal('50')
    result = reconcile(po, invoice)
    assert result['net_difference'] == '0'
    assert result['counts'] == {'difference': 1}


@pytest.mark.parametrize('field,value', [('quantity', None), ('unit_price', None), ('sku', None), ('unit', None), ('unit', 'pack')])
def test_unknown_or_incompatible_line_blocks_conclusion(field, value):
    po, invoice = pair()
    setattr(invoice.lines[0], field, value)
    result = reconcile(po, invoice)
    assert not result['complete']
    assert result['net_difference'] is None


@pytest.mark.parametrize('field,value', [('currency', 'USD'), ('currency', None), ('po_reference', 'OTHER'), ('supplier', 'OTHER'), ('supplier', None)])
def test_document_mismatch_blocks_conclusion(field, value):
    po, invoice = pair()
    setattr(invoice, field, value)
    result = reconcile(po, invoice)
    assert result['issues']
    assert result['net_difference'] is None


def test_duplicate_sku_is_not_arbitrarily_paired():
    po, invoice = pair()
    invoice.lines.append(invoice.lines[0].model_copy(update={'line_id': '2'}))
    result = reconcile(po, invoice)
    assert len(result['rows']) == 3
    assert result['counts'] == {'review': 3}
    assert result['net_difference'] is None


def test_missing_and_extra_items_keep_signed_difference():
    po, invoice = pair()
    invoice.lines[0].sku = 'B'
    result = reconcile(po, invoice)
    assert [r['delta'] for r in result['rows']] == ['-200', '200']
    assert result['counts'] == {'difference': 2}


def test_printed_amount_disagreement_is_visible():
    po, invoice = pair()
    invoice.lines[0].stated_total = Decimal('900')
    result = reconcile(po, invoice)
    assert result['counts'] == {'difference': 1}
    assert result['invoice_total'] == '200'


@pytest.mark.parametrize('currency,expected', [('USD', '0.02'), ('VND', '0')])
def test_round_each_line_before_summing(currency, expected):
    po, invoice = pair()
    for doc in (po, invoice):
        doc.currency = currency
        doc.lines = [Line(line_id=str(i), sku=str(i), unit='box', quantity='1', unit_price='0.005') for i in range(2)]
    assert reconcile(po, invoice)['po_total'] == expected


def test_zero_is_not_missing():
    po, invoice = pair()
    invoice.lines[0].unit_price = Decimal('0')
    result = reconcile(po, invoice)
    assert result['complete']
    assert result['net_difference'] == '-200'


def test_empty_documents_are_not_matched():
    po, invoice = pair()
    po.lines, invoice.lines = [], []
    assert not reconcile(po, invoice)['complete']


@pytest.mark.parametrize('value', ['NaN', 'Infinity', '-1', '1,000', '0.00001', '10000000000'])
def test_invalid_numbers_rejected(value):
    with pytest.raises(ValidationError):
        Line(line_id='1', quantity=value)


def test_duplicate_line_ids_rejected():
    po, _ = pair()
    data = po.model_dump()
    data['lines'] *= 2
    with pytest.raises(ValidationError):
        Document.model_validate(data)


def test_whitespace_headers_are_missing():
    assert Document(kind='PO', supplier='   ').supplier is None


def test_largest_supported_numbers_do_not_overflow_decimal_context():
    po, invoice = pair()
    for doc in (po, invoice):
        doc.currency = 'USD'
        doc.lines = [Line(line_id=str(i), sku=str(i), unit='box', quantity='9999999999.9999', unit_price='9999999999.9999') for i in range(200)]
    assert reconcile(po, invoice)['net_difference'] == '0.00'
