import hashlib
import importlib.util
import json
from datetime import date, timedelta
from pathlib import Path
import shutil
import sys
import subprocess
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).parent))
from fixtures import week, workbook, rewrite_xml
skill = Path(__file__).resolve().parents[1] / 'weekly-product-roi-report'
spec = importlib.util.spec_from_file_location('weekly_roi', skill / 'scripts/weekly_roi.py')
roi = importlib.util.module_from_spec(spec)
spec.loader.exec_module(roi)


class WeeklyReportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.inputs = self.base / 'inputs'
        self.paths = week(self.inputs)

    def tearDown(self):
        self.temp.cleanup()

    def rejected(self, pattern):
        target = self.base / 'failed-output'
        with self.assertRaisesRegex(roi.ReportError, pattern):
            roi.run(self.inputs, target, '2026-09-28')
        self.assertFalse(target.exists())

    def test_weighted_week_crosses_month_and_sources_preserved(self):
        before = [hashlib.sha256(p.read_bytes()).hexdigest() for p in self.paths]
        result = roi.run(self.inputs, self.base / 'report', '2026-09-28')
        analysis = json.loads(Path(result['analysis']).read_text(encoding='utf-8'))
        self.assertEqual(analysis['period']['dates'], [(date(2026, 9, 28) + timedelta(days=i)).isoformat() for i in range(7)])
        self.assertEqual(analysis['audit']['record_count'], 21)
        self.assertEqual(analysis['totals']['cost_cents'], 287000)
        self.assertEqual(analysis['totals']['sales_cents'], 850000)
        self.assertAlmostEqual(analysis['totals']['roi'], 8500 / 2870)
        self.assertNotAlmostEqual(analysis['totals']['roi'], sum(d['roi'] for d in analysis['daily_totals']) / 7)
        self.assertEqual(before, [hashlib.sha256(p.read_bytes()).hexdigest() for p in self.paths])
        self.assertEqual(analysis['audit']['blank_brushing_days'], 21)

    def test_zero_cost_ratio_is_unavailable(self):
        record = next(p for p in roi.analyze(self.inputs)['products'] if p['product'] == '合成产品乙')
        self.assertIsNone(record['roi'])
        self.assertTrue(all(r['roi'] is None for r in record['daily']))

    def test_paid_zero_sales_is_zero_ratio(self):
        record = next(p for p in roi.analyze(self.inputs)['products'] if p['product'] == '合成产品丙')
        self.assertEqual(record['roi'], 0)

    def test_all_zero_costs_valid(self):
        week(self.inputs, products=[{'name': '合成零费用', 'skus': ['zero-001'], 'cost': 0, 'sales': 0}])
        analysis = roi.analyze(self.inputs)
        self.assertIsNone(analysis['totals']['roi'])
        output = roi.run(self.inputs, self.base / 'zero-report')
        self.assertTrue(Path(output['html']).is_file())
        self.assertNotIn('NaN', roi.render(analysis).split('const data=', 1)[1].split(';', 1)[0])

    def test_explicit_week_excludes_previous_sunday(self):
        workbook(self.inputs / '日报_20260927.xlsx', date(2026, 9, 27))
        result = roi.analyze(self.inputs, '2026-09-28')
        self.assertEqual(result['audit']['record_count'], 21)
        self.assertEqual(result['audit']['ignored_outside_week_files'], ['日报_20260927.xlsx'])

    def test_missing_day(self):
        self.paths[2].unlink()
        self.rejected('2026-09-30.*实际 0')

    def test_duplicate_day(self):
        shutil.copy2(self.paths[0], self.inputs / '重复_20260928.xlsx')
        self.rejected('2026-09-28.*实际 2')

    def test_multiple_complete_weeks_need_selection(self):
        week(self.inputs, start=date(2026, 10, 5))
        with self.assertRaisesRegex(roi.ReportError, '指定 --week-start'):
            roi.analyze(self.inputs)

    def test_start_not_monday(self):
        with self.assertRaisesRegex(roi.ReportError, '周一'):
            roi.analyze(self.inputs, '2026-09-29')

    def test_wrong_in_sheet_date(self):
        workbook(self.paths[0], date(2026, 9, 28), date_offset=1)
        self.rejected('表内日期不一致')

    def test_stale_cost_cache(self):
        workbook(self.paths[0], date(2026, 9, 28), stale=True)
        self.rejected('费用缓存不一致')

    def test_missing_formula_cache(self):
        rewrite_xml(self.paths[0], lambda n, x: x.replace('<f>100+0</f><v>100</v>', '<f>100+0</f><v/>'))
        self.rejected('缺少数值或公式缓存')

    def test_stale_sales_cache(self):
        rewrite_xml(self.paths[0], lambda n, x: x.replace('<f>ROUND(1000+0,2)</f><v>1000</v>', '<f>ROUND(1000+0,2)</f><v>999</v>'))
        self.rejected('缓存不一致')

    def test_stale_total(self):
        rewrite_xml(self.paths[0], lambda n, x: x.replace('<f>SUM(C3:C5)</f><v>110</v>', '<f>SUM(C3:C5)</f><v>111</v>'))
        self.rejected('合计不一致')

    def test_missing_product_day(self):
        workbook(self.paths[0], date(2026, 9, 28), products=[{'name': '合成产品甲', 'skus': ['sample-001', 'sample-002'], 'cost': 100, 'sales': 1000}])
        self.rejected('缺少产品日记录')

    def test_sku_combination_conflict(self):
        rewrite_xml(self.paths[0], lambda n, x: x.replace('sample-002', 'sample-999'))
        self.rejected('SKU 绑定冲突')

    def test_sku_duplicate_in_combination(self):
        rewrite_xml(self.paths[0], lambda n, x: x.replace('sample-002', 'sample-001'))
        self.rejected('SKU 缺失或重复')

    def test_same_identity_name_change(self):
        rewrite_xml(self.paths[0], lambda n, x: x.replace('合成产品甲', '合成产品改名'))
        self.rejected('产品名变化')

    def test_blank_store_not_inferred_from_previous_row(self):
        rewrite_xml(self.paths[0], lambda n, x: x.replace('<c r="B4" t="inlineStr"><is><t>合成测试店</t></is></c>', '<c r="B4"/>') if 'sheet1' in n else x)
        self.rejected('缺少店铺身份')

    def test_no_overwrite_existing_run(self):
        output = self.base / 'existing'
        output.mkdir()
        marker = output / 'keep.txt'
        marker.write_text('preserved')
        with self.assertRaisesRegex(roi.ReportError, '输出目录已存在'):
            roi.run(self.inputs, output)
        self.assertEqual(marker.read_text(), 'preserved')

    def test_safe_html_escaping(self):
        attack = '</script><script>window.BAD=true</script>'
        week(self.inputs, products=[{'name': attack, 'skus': ['escape-001'], 'cost': 1, 'sales': 2}])
        html = roi.render(roi.analyze(self.inputs))
        self.assertNotIn(attack, html)
        self.assertIn('\\u003c/script\\u003e', html)
        self.assertNotIn('window.openai', html)
        self.assertNotIn('<script src=', html)

    def test_formula_code_not_executed(self):
        with self.assertRaises(roi.ReportError):
            roi.arithmetic("__import__('os').system('anything')")

    def test_corrupt_xlsx_returns_json_failure_without_report(self):
        self.paths[0].write_bytes(b'not an XLSX archive')
        output = self.base / 'corrupt-output'
        result = subprocess.run([sys.executable, '-I', str(skill / 'scripts/weekly_roi.py'), 'run',
                                 '--input-dir', str(self.inputs), '--output-dir', str(output),
                                 '--week-start', '2026-09-28'], capture_output=True, encoding='utf-8')
        self.assertEqual(result.returncode, 2)
        failure = json.loads(result.stderr)
        self.assertEqual(failure['status'], 'FAIL')
        self.assertIn('zip', failure['reason'].lower())
        self.assertFalse(output.exists())


if __name__ == '__main__':
    unittest.main()
