"""Create synthetic complete-week reports for offline browser acceptance."""
import argparse
import importlib.util
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).parent))
from fixtures import week

parser = argparse.ArgumentParser()
parser.add_argument('--workspace', type=Path, required=True)
parser.add_argument('--mode', choices=['standard', 'zero', 'escaped'], default='standard')
args = parser.parse_args()
root = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('weekly_roi', root / 'weekly-product-roi-report/scripts/weekly_roi.py')
roi = importlib.util.module_from_spec(spec)
spec.loader.exec_module(roi)
products = None
if args.mode == 'zero':
    products = [{'name': '合成零费用', 'skus': ['zero-001'], 'cost': 0, 'sales': 0}]
elif args.mode == 'escaped':
    products = [{'name': '</script><script>window.BAD=true</script>', 'skus': ['escape-001'], 'cost': 1, 'sales': 2}]
week(args.workspace / 'inputs', products=products)
print(roi.run(args.workspace / 'inputs', args.workspace / 'report'))
