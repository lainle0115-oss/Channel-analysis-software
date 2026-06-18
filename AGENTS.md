# Retail Channel AI Assistant Agent Guide

## Project Commands

```bash
cd /Users/cocachloe/Documents/职业/retail-channel-ai-assistant
source .venv/bin/activate
pytest -q
./scripts/start_app.sh
./scripts/status_app.sh
./scripts/restart_app.sh
```

The local app is expected at `http://127.0.0.1:8501/`.

Automatic file watching is disabled for stability. After code changes, run
`./scripts/restart_app.sh` before browser verification. Runtime logs are written
to `logs/streamlit.log`.

## Business Semantics

- Sales quantity and sales amount are additive across the selected date range.
- Inventory is a snapshot metric. Current or latest inventory must never sum the
  same channel and SKU across dates.
- Use `src.retail_assistant.analytics.latest_inventory_rows()` before aggregating
  current or latest inventory by channel, SKU, city, report, or export.
- Xiaoxiang row inventory is the sum of warehouse, front-station, supplier-to-
  warehouse transit, and warehouse-to-store transit components.
- Hema sales rows must keep only records whose `经营店名称` contains `店`; this
  excludes FDC, front warehouses, and other non-store records.
- Hema inventory uses the latest available `库存总数`.
- Missing sales amount is a coverage limitation. Never substitute settlement or
  purchase amount as GMV.
- Weekly reports use the full natural Monday-Sunday period. Monthly reports use
  the full calendar month. Show missing-day coverage instead of shrinking periods.

## Verification

- Run `pytest -q` and `python -m py_compile app.py src/retail_assistant/*.py`.
- For UI changes, verify the rendered app in the browser at
  `http://127.0.0.1:8501/`.
- Confirm the hero is not covered by the Streamlit header, uploader controls are
  readable, charts render, and empty states are explicit.
- For inventory changes, reconcile KPI, channel summary, SKU summary, report
  tables, and Word/Excel export paths against the same latest-snapshot total.

## Document Map

- `README.md`: capabilities, setup, workflow, and durable metric definitions.
- `docs/DEMO_RUNBOOK.md`: business-facing 5-8 minute demo path, expected evidence,
  boundary language, and pre-demo checks.

Keep implementation history out of this file. Update these rules only when the
current product contract changes.
