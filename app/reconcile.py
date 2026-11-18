from collections import Counter
from decimal import Decimal, ROUND_HALF_UP

from .models import Document, Line


def money(value: Decimal, currency: str | None):
    step = Decimal('1') if currency == 'VND' else Decimal('0.01')
    return value.quantize(step, rounding=ROUND_HALF_UP)


def line_total(line: Line, currency: str | None):
    if line.quantity is None or line.unit_price is None:
        return None
    return money(line.quantity * line.unit_price, currency)


def reconcile(po: Document, invoice: Document):
    if po.kind != 'PO' or invoice.kind != 'INVOICE':
        raise ValueError('Chọn đúng PO và hóa đơn.')
    issues = []
    if not po.lines or not invoice.lines:
        issues.append('Thiếu dòng hàng trên một chứng từ.')
    if not po.currency or not invoice.currency:
        issues.append('Chưa xác định tiền tệ trên cả hai chứng từ.')
    elif po.currency != invoice.currency:
        issues.append('Hai chứng từ khác tiền tệ; không quy đổi tự động.')
    if not po.number or not invoice.po_reference:
        issues.append('Thiếu mã PO hoặc mã PO tham chiếu trên hóa đơn.')
    elif po.number.strip().casefold() != invoice.po_reference.strip().casefold():
        issues.append('Hóa đơn tham chiếu một mã PO khác.')
    if not po.supplier or not invoice.supplier:
        issues.append('Thiếu tên nhà cung cấp.')
    elif po.supplier.strip().casefold() != invoice.supplier.strip().casefold():
        issues.append('Tên nhà cung cấp khác nhau; cần kiểm tra cặp chứng từ.')
    if po.currency and po.currency not in ('VND', 'USD', 'EUR'):
        issues.append('Bản này chỉ hỗ trợ quy tắc làm tròn VND, USD và EUR.')

    key = lambda line: (line.sku or '').strip().casefold()
    pc, ic = Counter(key(l) for l in po.lines), Counter(key(l) for l in invoice.lines)
    ambiguous = {sku for sku in pc.keys() | ic.keys() if not sku or pc[sku] > 1 or ic[sku] > 1}
    rows, used = [], set()
    inv_by_sku = {key(l): l for l in invoice.lines if key(l) not in ambiguous}

    def compare_line(p, i):
        notes, blocked = [], bool(issues)
        if any(key(l) in ambiguous for l in (p, i) if l):
            notes.append('Thiếu hoặc trùng SKU; cần xác định dòng tương ứng.')
            blocked = True
        if p is None:
            notes.append('Có trên hóa đơn, chưa tìm thấy trên PO.')
        elif i is None:
            notes.append('Có trên PO, chưa tìm thấy trên hóa đơn.')
        else:
            if not p.unit or not i.unit or p.unit.casefold() != i.unit.casefold():
                notes.append('Đơn vị tính thiếu hoặc khác nhau.')
                blocked = True
            if p.quantity is not None and i.quantity is not None and p.quantity != i.quantity:
                notes.append('Chênh lệch số lượng.')
            if p.unit_price is not None and i.unit_price is not None and p.unit_price != i.unit_price:
                notes.append('Chênh lệch đơn giá.')
        for label, line, currency in [('PO', p, po.currency), ('Hóa đơn', i, invoice.currency)]:
            if line:
                if not line.unit:
                    notes.append(f'{label}: thiếu đơn vị tính.')
                    blocked = True
                calculated = line_total(line, currency)
                if calculated is None:
                    notes.append(f'{label}: thiếu số lượng hoặc đơn giá.')
                    blocked = True
                elif line.stated_total is not None and money(line.stated_total, currency) != calculated:
                    notes.append(f'{label}: thành tiền ghi trên chứng từ khác phép nhân.')
        pt = line_total(p, po.currency) if p else Decimal(0)
        it = line_total(i, invoice.currency) if i else Decimal(0)
        delta = None if blocked or pt is None or it is None else it - pt
        return {
            'sku': (i or p).sku, 'description': (i or p).description,
            'po_line': p.model_dump(mode='json') if p else None,
            'invoice_line': i.model_dump(mode='json') if i else None,
            'status': 'review' if blocked else ('difference' if notes else 'matched'),
            'notes': notes or (['Kiểm tra thông tin chứng từ.'] if blocked else ['Khớp số lượng, đơn vị và đơn giá.']),
            'po_amount': str(pt) if pt is not None else None,
            'invoice_amount': str(it) if it is not None else None,
            'delta': str(delta) if delta is not None else None,
        }

    for p in po.lines:
        i = inv_by_sku.get(key(p)) if key(p) not in ambiguous else None
        if i:
            used.add(i.line_id)
        rows.append(compare_line(p, i))
    for i in invoice.lines:
        if i.line_id not in used:
            rows.append(compare_line(None, i))

    def total(doc):
        amounts = [line_total(l, doc.currency) for l in doc.lines]
        return sum(amounts, Decimal(0)) if amounts and all(a is not None for a in amounts) else None

    pt, it = total(po), total(invoice)
    complete = not issues and all(r['status'] != 'review' for r in rows)
    delta = it - pt if complete and pt is not None and it is not None else None
    return {
        'currency': po.currency if po.currency == invoice.currency else None,
        'po_total': str(pt) if pt is not None else None,
        'invoice_total': str(it) if it is not None else None,
        'net_difference': str(delta) if delta is not None else None,
        'issues': issues, 'rows': rows, 'complete': complete,
        'counts': dict(Counter(r['status'] for r in rows)),
        'basis': 'Tổng trước thuế/chiết khấu, tính từ số lượng × đơn giá. Chênh lệch = hóa đơn − PO.',
    }
