from pathlib import Path
import pymupdf as fitz

ROOT = Path(__file__).resolve().parents[1]
ROWS = {
    'purchase-order': [('PAPER-A4', 'Giấy A4', '20', 'ram', '150000', '3000000'), ('PEN-BLUE', 'Bút xanh', '50', 'cây', '5000', '250000')],
    'invoice': [('PAPER-A4', 'Giấy A4', '20', 'ram', '165000', '3300000'), ('PEN-BLUE', 'Bút xanh', '60', 'cây', '5000', '300000'), ('FOLDER', 'Bìa hồ sơ', '10', 'cái', '12000', '120000')],
}


def generate():
    target = ROOT / 'samples'
    target.mkdir(exist_ok=True)
    font_path = Path('C:/Windows/Fonts/arial.ttf')
    for name, rows in ROWS.items():
        doc = fitz.open()
        page = doc.new_page(width=595, height=842)
        font = 'helv'
        if font_path.exists():
            page.insert_font(fontname='body', fontfile=str(font_path))
            font = 'body'
        def put(y, text, size=11):
            page.insert_text((42, y), text, fontname=font, fontsize=size, color=(.12, .14, .17))
        put(52, 'RECONCILE SAMPLE v1', 10)
        put(96, 'PURCHASE ORDER' if name == 'purchase-order' else 'INVOICE', 24)
        put(126, 'DEMO DATA - NOT A REAL TRANSACTION', 10)
        put(176, 'Number: PO-001' if name == 'purchase-order' else 'Number: INV-001')
        if name == 'invoice':
            put(201, 'PO reference: PO-001')
        put(226, 'Supplier: Minh An Stationery (demo)')
        put(251, 'Currency: VND')
        put(276, 'Basis: before tax and discounts')
        page.draw_line((42, 302), (553, 302), color=(.75, .75, .75))
        put(326, 'SKU | Description | Quantity | Unit | Unit price | Amount', 10)
        for index, row in enumerate(rows):
            put(362 + 44*index, ' | '.join(row), 10)
        total = sum(int(row[5]) for row in rows)
        put(558, f'Subtotal: {total} VND', 16)
        put(604, 'Created for testing extraction and line-item comparison.', 10)
        doc.save(target / f'{name}.pdf')
        doc.close()


if __name__ == '__main__':
    generate()
