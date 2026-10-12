"""Explicit two-week candidate mode; simple weekly_roi.py remains unchanged."""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import date, timedelta
from decimal import Decimal
from html import escape
import json
from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parent))
import weekly_roi as base

VERSION = '0.2.0-rc.2'


def change(previous, current):
    """Never fabricate a percent for missing, undefined, or zero baseline."""
    if previous is None or current is None:
        return {'delta': None, 'pct': None, 'reason': 'unavailable'}
    delta = current - previous
    pct = float((Decimal(str(current)) / Decimal(str(previous)) - 1) * 100) if previous > 0 else None
    return {'delta': delta, 'pct': pct, 'reason': 'baseline_zero' if previous == 0 else None}


def assemble(previous, current):
    old_start = date.fromisoformat(previous['period']['start'])
    new_start = date.fromisoformat(current['period']['start'])
    base.require(old_start.weekday() == new_start.weekday() == 0 and (new_start - old_start).days == 7,
                 '环比必须比较相邻的两个完整周一至周日自然周')
    for week in (previous, current):
        expected_dates = [(date.fromisoformat(week['period']['start']) + timedelta(days=i)).isoformat() for i in range(7)]
        base.require(week['period']['dates'] == expected_dates, '每周须有完整且连续的七天')
        for product in week['products']:
            base.require([d['date'] for d in product['daily']] == expected_dates, '产品缺少日记录，不能补零')
    by_week = [{p['key']: p for p in week['products']} for week in (previous, current)]
    names, sku_bindings = {}, {}
    for week in (previous, current):
        for product in week['products']:
            key = product['key']
            base.require(key not in names or names[key] == product['product'], '跨周同 SKU 产品名变化，须核对身份')
            names[key] = product['product']
            for sku in product['skus']:
                identity = (product['store'], sku)
                base.require(identity not in sku_bindings or sku_bindings[identity] == key,
                             '跨周 SKU 组合绑定冲突，不能自动合并为同一单品')
                sku_bindings[identity] = key
    products = []
    for key in set(by_week[0]) | set(by_week[1]):
        old, new = [w.get(key) for w in by_week]
        info = new or old
        membership = 'both' if old and new else ('current_only' if new else 'previous_only')
        changes = {metric: change(old.get(metric) if old else None, new.get(metric) if new else None)
                   for metric in ('roi', 'cost_cents', 'sales_cents')}
        products.append({'key': key, 'product': info['product'], 'store': info['store'], 'skus': info['skus'],
                         'membership': membership, 'previous': old, 'current': new, 'changes': changes})
    products.sort(key=lambda p: (-(p['current']['cost_cents'] if p['current'] else -1), p['key']))
    total_changes = {metric: change(previous['totals'][metric], current['totals'][metric])
                     for metric in ('roi', 'cost_cents', 'sales_cents')}
    matched = [p for p in products if p['membership'] == 'both']
    matched_totals = []
    for side in ('previous', 'current'):
        cost = sum(p[side]['cost_cents'] for p in matched)
        sales = sum(p[side]['sales_cents'] for p in matched)
        matched_totals.append({'cost_cents': cost, 'sales_cents': sales, 'roi': base.ratio(cost, sales)})
    return {'version': VERSION, 'mode': 'two_complete_natural_weeks',
            'previous': previous, 'current': current, 'products': products,
            'totals': {'previous': previous['totals'], 'current': current['totals'], 'changes': total_changes},
            'matched_totals': {'previous': matched_totals[0], 'current': matched_totals[1]},
            'audit': {'status': 'PASS', 'weeks': 2, 'source_count': len(previous['sources']) + len(current['sources']),
                      'record_count': previous['audit']['record_count'] + current['audit']['record_count'],
                      'matched_products': len(matched), 'current_only_products': sum(p['membership'] == 'current_only' for p in products),
                      'previous_only_products': sum(p['membership'] == 'previous_only' for p in products),
                      'cross_week_sku_bindings_stable': True, 'scope': previous['audit']['scope']}}


def analyze(input_dir, current_week_start):
    current_start = date.fromisoformat(current_week_start)
    base.require(current_start.weekday() == 0, '--week-start 必须是本周周一')
    previous_start = current_start - timedelta(days=7)
    previous = base.analyze(input_dir, previous_start.isoformat())
    current = base.analyze(input_dir, current_start.isoformat())
    return assemble(previous, current)


def render(analysis):
    def display_week(record):
        if record is None:
            return None
        result = {'cost': record['cost_cents'], 'sales': record['sales_cents'], 'roi': record['roi']}
        if 'daily' in record:
            result['days'] = [display_week(d) for d in record['daily']]
        return result
    labels = Counter(p['product'] for p in analysis['products'])
    data = {'version': VERSION, 'periods': [analysis[side]['period'] for side in ('previous', 'current')],
            'products': [{'id': p['key'], 'name': p['product'] if labels[p['product']] == 1
                          else f"{p['product']}（{p['store']} / {','.join(p['skus'])}）",
                          'membership': p['membership'], 'previous': display_week(p['previous']),
                          'current': display_week(p['current']), 'changes': p['changes']} for p in analysis['products']],
            'totals': {'previous': display_week(analysis['totals']['previous']), 'current': display_week(analysis['totals']['current']),
                       'changes': analysis['totals']['changes']},
            'dailyTotals': [[display_week(d) for d in analysis[side]['daily_totals']] for side in ('previous', 'current')],
            'audit': analysis['audit']}
    payload = json.dumps(data, ensure_ascii=False, separators=(',', ':'), allow_nan=False)
    payload = payload.replace('<', '\\u003c').replace('>', '\\u003e').replace('&', '\\u0026')
    title = f"单品自然周环比报告 {analysis['current']['period']['start']}—{analysis['current']['period']['end']}"
    template = (base.SKILL / 'assets/comparison.html').read_text(encoding='utf-8')
    replacements = {'__TITLE__': escape(title), '__ROI_DATA__': payload,
                    '__D3__': (base.SKILL / 'assets/d3-7.9.0.min.js').read_text(encoding='utf-8').replace('</script', '<\\/script'),
                    '__D3_LICENSE__': escape((base.SKILL / 'assets/D3-LICENSE.txt').read_text(encoding='utf-8'))}
    for placeholder, value in replacements.items():
        base.require(template.count(placeholder) == 1, f'模板占位符不唯一: {placeholder}')
        template = template.replace(placeholder, value)
    return template


def run(input_dir, output_dir, current_week_start):
    analysis = analyze(input_dir, current_week_start)
    html = render(analysis)
    base.require(not output_dir.exists(), '输出目录已存在；请使用新的运行目录')
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix='.roi-comparison-', dir=output_dir.parent))
    try:
        filename = f"weekly-roi-comparison-{analysis['current']['period']['start']}-{analysis['current']['period']['end']}.html"
        (stage / filename).write_text(html, encoding='utf-8')
        (stage / 'analysis.json').write_text(json.dumps(analysis, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')
        stage.rename(output_dir)
    finally:
        if stage.exists():
            for child in stage.iterdir():
                child.unlink()
            stage.rmdir()
    return {'status': 'COMPLETE', 'version': VERSION, 'html': str((output_dir / filename).resolve()),
            'analysis': str((output_dir / 'analysis.json').resolve()), 'audit': analysis['audit'],
            'totals': analysis['totals']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input-dir', type=Path, required=True)
    parser.add_argument('--week-start', required=True, help='Current Monday, YYYY-MM-DD')
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args()
    try:
        result = run(args.input_dir.resolve(), args.output_dir.resolve(), args.week_start)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (base.ReportError, ValueError, OSError, ImportError, KeyError, base.BadZipFile, base.ParseError) as exc:
        print(json.dumps({'status': 'FAIL', 'reason': str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == '__main__':
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    raise SystemExit(main())
