"""Reproducible synthetic browser boundary: low ROI, zero bases, missing week."""
import argparse
import importlib.util
from datetime import date
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent))
from fixtures import week
parser=argparse.ArgumentParser()
parser.add_argument('--workspace',type=Path,required=True)
args=parser.parse_args()
skill=Path(__file__).resolve().parents[1]/'weekly-product-roi-report'
spec=importlib.util.spec_from_file_location('compare_weeks',skill/'scripts/compare_weeks.py')
compare=importlib.util.module_from_spec(spec)
spec.loader.exec_module(compare)
old=[{'name':'合成低投产','skus':['roi-small'],'cost':10,'sales':5},
     {'name':'合成无销','skus':['zero-base'],'cost':2,'sales':0},
     {'name':'合成零费用','skus':['no-cost'],'cost':0,'sales':3},
     {'name':'合成零记录','skus':['zero-both'],'cost':0,'sales':0},
     {'name':'合成仅上周','skus':['previous-only'],'cost':.2,'sales':.1}]
new=[{'name':'合成低投产','skus':['roi-small'],'cost':10,'sales':6},
     {'name':'合成无销','skus':['zero-base'],'cost':2,'sales':4},
     {'name':'合成零费用','skus':['no-cost'],'cost':0,'sales':6},
     {'name':'合成零记录','skus':['zero-both'],'cost':0,'sales':0},
     {'name':'合成仅本周','skus':['current-only'],'cost':.01,'sales':.03}]
week(args.workspace/'inputs',date(2026,9,28),old)
week(args.workspace/'inputs',date(2026,10,5),new)
print(compare.run(args.workspace/'inputs',args.workspace/'report','2026-10-05'))
