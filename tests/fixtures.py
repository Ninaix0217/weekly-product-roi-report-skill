"""Synthetic minimal OOXML fixtures. No real workbooks or business identities."""
from datetime import date, timedelta
from html import escape
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED


def cell(ref, value=None, formula=None, kind=None):
    if formula is not None:
        return f'<c r="{ref}"><f>{escape(formula.removeprefix("="))}</f><v>{value}</v></c>'
    if value is None:
        return f'<c r="{ref}"/>'
    if isinstance(value, str) and kind != 'd':
        return f'<c r="{ref}" t="inlineStr"><is><t>{escape(value)}</t></is></c>'
    return f'<c r="{ref}"' + (' t="d"' if kind == 'd' else '') + f'><v>{value}</v></c>'


def workbook(path, day, index=0, products=None, stale=False, date_offset=0):
    # Deliberately varying expenses makes a daily-average ROI incorrect.
    products = products if products is not None else [
        {'name': '合成产品甲', 'skus': ['sample-001', 'sample-002'], 'cost': (index + 1) * 100, 'sales': 1000},
        {'name': '合成产品乙', 'skus': ['sample-003'], 'cost': 0, 'sales': 500 if index % 2 else 0},
        {'name': '合成产品丙', 'skus': ['sample-004'], 'cost': 10, 'sales': 0},
    ]
    ns = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'
    main = '<worksheet xmlns="' + ns + '"><sheetData>'
    main += '<row r="1">' + cell('A1', '产品（单盒和三盒）') + cell('B1', '店铺') + cell('C1', (day + timedelta(days=date_offset)).isoformat() + 'T00:00:00', kind='d') + '</row>'
    main += '<row r="2">' + cell('C2', '付费总费用') + cell('D2', '真实销售额（扣除刷单）') + cell('E2', '综合投产比') + '</row>'
    linked = '<worksheet xmlns="' + ns + '"><sheetData><row r="2">' + cell('B2', '单盒SKU') + cell('C2', '三盒sku') + '</row>'
    for i, product in enumerate(products, 3):
        cost, sales = product['cost'], product['sales']
        roi = sales / cost if cost else 0
        main += f'<row r="{i}">' + cell(f'A{i}', product['name']) + cell(f'B{i}', '合成测试店') + cell(f'C{i}', cost + (1 if stale and i == 3 else 0), formula=f'{cost}+0') + cell(f'D{i}', sales, formula=f"='销售来源'!F{i}") + cell(f'E{i}', roi, formula=f'IF(C{i}=0,0,D{i}/C{i})') + '</row>'
        linked += f'<row r="{i}">' + cell(f'A{i}', product['name']) + cell(f'B{i}', product['skus'][0]) + cell(f'C{i}', product['skus'][1] if len(product['skus']) > 1 else None) + cell(f'D{i}', sales, formula=f'ROUND({sales}+0,2)') + cell(f'E{i}') + cell(f'F{i}', sales, formula=f'ROUND(D{i}-E{i},2)') + '</row>'
    totalrow = len(products) + 3
    cost = sum(p['cost'] for p in products)
    sales = sum(p['sales'] for p in products)
    main += f'<row r="{totalrow}">' + cell(f'A{totalrow}', '合计') + cell(f'C{totalrow}', cost, formula=f'SUM(C3:C{totalrow - 1})') + cell(f'D{totalrow}', sales, formula=f'SUM(D3:D{totalrow - 1})') + cell(f'E{totalrow}', sales / cost if cost else 0, formula=f'IF(C{totalrow}=0,0,D{totalrow}/C{totalrow})') + '</row></sheetData></worksheet>'
    linked += '</sheetData></worksheet>'
    contents = '<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>' + ''.join(f'<Override PartName="/xl/worksheets/sheet{i}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>' for i in (1, 2)) + '</Types>'
    relationships = '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>'
    book = '<workbook xmlns="' + ns + '" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="综合表" sheetId="1" r:id="rId1"/><sheet name="销售来源" sheetId="2" r:id="rId2"/></sheets></workbook>'
    bookrels = '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">' + ''.join(f'<Relationship Id="rId{i}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet{i}.xml"/>' for i in (1, 2)) + '</Relationships>'
    path.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(path, 'w', ZIP_DEFLATED) as archive:
        for name, text in {'[Content_Types].xml': contents, '_rels/.rels': relationships,
                           'xl/workbook.xml': book, 'xl/_rels/workbook.xml.rels': bookrels,
                           'xl/worksheets/sheet1.xml': main, 'xl/worksheets/sheet2.xml': linked}.items():
            archive.writestr(name, text)


def week(directory, start=date(2026, 9, 28), products=None):
    paths = []
    for i in range(7):
        day = start + timedelta(days=i)
        path = directory / f'每日综合投产登记_{day:%Y%m%d}_已填写.xlsx'
        workbook(path, day, i, products=products)
        paths.append(path)
    return paths


def rewrite_xml(path, replace):
    with ZipFile(path) as archive:
        entries = {name: archive.read(name) for name in archive.namelist()}
    for name, content in entries.items():
        if name.startswith('xl/worksheets/'):
            entries[name] = replace(name, content.decode('utf-8')).encode('utf-8')
    with ZipFile(path, 'w', ZIP_DEFLATED) as archive:
        for name, content in entries.items():
            archive.writestr(name, content)
