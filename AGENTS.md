# Project scope

Maintain `weekly-product-roi-report/` as a portable Codex skill. The default is the simple offline natural-week report. Do not add comparison, operating states, or ERP analytics without an explicit request. Keep the upstream Daily ROI skill unchanged.

Read raw workbooks only; generated reports and private acceptance runs must stay outside this repository. Commit no user spreadsheets, actual product mappings, historical report outputs or local absolute paths. Synthetic tests are fine.

Changes to accounting or input validation need observable regression checks. Browser changes need offline desktop/mobile verification and actual screenshot review. A data PASS is not proof of upstream ERP/finance truth or native Excel recalculation.
