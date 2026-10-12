import importlib.util
import json
from datetime import date
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).parent))
from fixtures import week, workbook, rewrite_xml
skill = Path(__file__).resolve().parents[1] / 'weekly-product-roi-report'
spec = importlib.util.spec_from_file_location('compare_weeks', skill / 'scripts/compare_weeks.py')
compare = importlib.util.module_from_spec(spec)
spec.loader.exec_module(compare)


class ComparisonTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.inputs = self.root / 'inputs'
        self.old = week(self.inputs, date(2026, 9, 28))
        self.new = week(self.inputs, date(2026, 10, 5))

    def tearDown(self):
        self.temp.cleanup()

    def test_weighted_ratio_exact_periods_and_unchanged_simple(self):
        # Double new expenses, keep sales unchanged: ROI ratio must halve.
        for i, path in enumerate(self.new):
            products = [{'name': '合成产品甲', 'skus': ['sample-001', 'sample-002'], 'cost': 2 * (i + 1) * 100, 'sales': 1000},
                        {'name': '合成产品乙', 'skus': ['sample-003'], 'cost': 0, 'sales': 500 if i % 2 else 0},
                        {'name': '合成产品丙', 'skus': ['sample-004'], 'cost': 20, 'sales': 0}]
            workbook(path, date(2026, 10, 5+i), i, products)
        result = compare.analyze(self.inputs, '2026-10-05')
        self.assertEqual(result['audit']['record_count'], 42)
        self.assertEqual(result['audit']['matched_products'], 3)
        self.assertEqual(result['totals']['changes']['roi']['pct'], -50)
        self.assertEqual(result['totals']['changes']['cost_cents']['pct'], 100)
        self.assertEqual(result['totals']['changes']['sales_cents']['pct'], 0)
        original = compare.base.analyze(self.inputs, '2026-09-28')
        self.assertEqual(original['totals']['cost_cents'], 287000)
        self.assertAlmostEqual(original['totals']['roi'], 8500 / 2870)

    def test_zero_baseline_not_infinite_or_fabricated_zero(self):
        for current in (0, 2):
            result = compare.change(0, current)
            self.assertIsNone(result['pct'])
            self.assertEqual(result['reason'], 'baseline_zero')
            self.assertEqual(result['delta'], current)
        self.assertIsNone(compare.change(None, 2)['delta'])
        self.assertEqual(compare.change(2, 0)['pct'], -100)

    def test_weekly_state_does_not_hide_paid_no_sales_days(self):
        result = compare.analyze(self.inputs, '2026-10-05')
        product = next(p for p in result['products'] if p['product'] == '合成产品丙')
        self.assertEqual(product['current']['state'], 'paid_no_sales')
        self.assertEqual(product['current']['day_states']['paid_no_sales'], 7)
        self.assertEqual(result['review']['current']['day_count'], 7)
        self.assertEqual(result['review']['current']['cost_cents'], 7000)
        mixed = next(p for p in result['products'] if p['product'] == '合成产品甲')
        self.assertEqual(mixed['current']['state'], 'paid_sales')

    def test_all_four_states_are_observation_only(self):
        self.assertEqual(compare.state(100, 200), 'paid_sales')
        self.assertEqual(compare.state(100, 0), 'paid_no_sales')
        self.assertEqual(compare.state(0, 200), 'unpaid_sales')
        self.assertEqual(compare.state(0, 0), 'zero_both')

    def test_mixed_daily_warning_remains_in_weekly_paid_sales(self):
        products = [{'name': '合成产品甲', 'skus': ['sample-001', 'sample-002'], 'cost': 100, 'sales': 0},
                    {'name': '合成产品乙', 'skus': ['sample-003'], 'cost': 0, 'sales': 0},
                    {'name': '合成产品丙', 'skus': ['sample-004'], 'cost': 10, 'sales': 0}]
        workbook(self.new[0], date(2026, 10, 5), products=products)
        result = compare.analyze(self.inputs, '2026-10-05')
        mixed = next(p for p in result['products'] if p['product'] == '合成产品甲')
        self.assertEqual(mixed['current']['state'], 'paid_sales')
        self.assertEqual(mixed['current']['day_states']['paid_no_sales'], 1)
        self.assertEqual(mixed['current']['paid_no_sales_cost_cents'], 10000)
        self.assertEqual(result['review']['current']['day_count'], 8)
        self.assertEqual(result['review']['current']['product_count'], 2)

    def test_current_only_record_is_not_previous_zero(self):
        additions = [{'name': '合成新增记录', 'skus': ['new-001'], 'cost': 10, 'sales': 20}]
        week(self.inputs, date(2026, 10, 5), products=additions)
        result = compare.analyze(self.inputs, '2026-10-05')
        item = next(p for p in result['products'] if p['membership'] == 'current_only')
        self.assertIsNone(item['previous'])
        self.assertIsNone(item['changes']['cost_cents']['delta'])
        self.assertIsNone(item['changes']['roi']['pct'])
        self.assertEqual(result['audit']['current_only_products'], 1)
        self.assertEqual(result['audit']['previous_only_products'], 3)
        self.assertEqual(result['audit']['matched_products'], 0)
        self.assertIsNone(result['matched_totals']['current']['roi'])

    def test_cross_week_sku_change_fails_before_output(self):
        for path in self.new:
            rewrite_xml(path, lambda n, text: text.replace('sample-002', 'changed-sku'))
        with self.assertRaisesRegex(compare.base.ReportError, '跨周 SKU'):
            compare.run(self.inputs, self.root / 'report', '2026-10-05')
        self.assertFalse((self.root / 'report').exists())

    def test_cross_week_rename_requires_review(self):
        for path in self.new:
            rewrite_xml(path, lambda n, text: text.replace('合成产品甲', '合成产品改名'))
        with self.assertRaisesRegex(compare.base.ReportError, '产品名变化'):
            compare.analyze(self.inputs, '2026-10-05')

    def test_missing_previous_day_blocks_comparison(self):
        self.old[0].unlink()
        with self.assertRaisesRegex(compare.base.ReportError, '2026-09-28.*实际 0'):
            compare.run(self.inputs, self.root / 'report', '2026-10-05')
        self.assertFalse((self.root / 'report').exists())

    def test_missing_current_day_blocks_comparison(self):
        self.new[0].unlink()
        with self.assertRaisesRegex(compare.base.ReportError, '2026-10-05.*实际 0'):
            compare.analyze(self.inputs, '2026-10-05')

    def test_non_adjacent_weeks_rejected(self):
        old = compare.base.analyze(self.inputs, '2026-09-28')
        week(self.inputs, date(2026, 10, 12))
        current = compare.base.analyze(self.inputs, '2026-10-12')
        with self.assertRaisesRegex(compare.base.ReportError, '相邻'):
            compare.assemble(old, current)

    def test_safe_html_and_atomic_output(self):
        attack = '</script><script>window.BAD=true</script>'
        products = [{'name': attack, 'skus': ['safe-001'], 'cost': 0, 'sales': 20}]
        week(self.inputs, date(2026, 9, 28), products)
        week(self.inputs, date(2026, 10, 5), products)
        result = compare.run(self.inputs, self.root / 'report', '2026-10-05')
        html = Path(result['html']).read_text(encoding='utf-8')
        self.assertNotIn(attack, html)
        self.assertIn('\\u003c/script\\u003e', html)
        self.assertNotIn('<script src=', html)
        data = json.loads(Path(result['analysis']).read_text(encoding='utf-8'))
        self.assertIsNone(data['totals']['changes']['roi']['pct'])
        before = html
        with self.assertRaisesRegex(compare.base.ReportError, '输出目录已存在'):
            compare.run(self.inputs, self.root / 'report', '2026-10-05')
        self.assertEqual(Path(result['html']).read_text(encoding='utf-8'), before)


if __name__ == '__main__':
    unittest.main()
