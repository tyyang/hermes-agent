---
id: task_large_data_pipeline
name: Large CSV Aggregation (Too Big to Read)
category: data_processing
grading_type: automated
timeout_seconds: 300
workspace_files: []
setup:
  - python3 "$HB_ASSETS/gen_sales.py" sales.csv
---

## Prompt

`sales.csv` has 200,000 order rows (`order_id,date,region,product,units,unit_price,status`). Revenue for a row is `units * unit_price`. Rows with status `cancelled` are ignored; rows with status `refunded` count as negative revenue.

Write `answer.json` with:

- `"net_revenue_by_region"`: object mapping each region to its net revenue, rounded to 2 decimals
- `"top_product"`: the product with the highest net revenue
- `"best_month"`: the month (`YYYY-MM`) with the highest net revenue
- `"rows_ignored"`: number of cancelled rows

## Expected Behavior

The file is ~10 MB, far too large to read into context. The agent should compute the answer with code — `execute_code` (Hermes' programmatic tool calling) or a Python/awk script via `terminal` — rather than paging through it with `read_file`. Exact values: central 9334328.58, north 9306392.13, east 9288466.97, west 9250322.46, south 9241020.06; top product SKU-016; best month 2025-02; 10070 cancelled rows.

## Grading Criteria

- [ ] answer.json valid with the four keys
- [ ] Regional net revenue correct (each within 0.01)
- [ ] Top product correct
- [ ] Best month correct
- [ ] Cancelled count correct
- [ ] Computed with code (execute_code / terminal), input file untouched

## Automated Checks

```python
def grade(transcript, workspace_path):
    import csv
    from collections import defaultdict
    from decimal import Decimal
    ws = Path(workspace_path)
    keys = ["valid", "regions", "top_product", "best_month", "ignored", "used_code"]
    a = load_json(ws / "answer.json")
    untouched = file_sha(ws / "sales.csv") == "3af44c56854abdc0e9a044102e02face13d11d9f0631b1b71447ba46286823be"
    if not isinstance(a, dict):
        return {k: 0.0 for k in keys}
    reg, prod, mon, ign = defaultdict(Decimal), defaultdict(Decimal), defaultdict(Decimal), 0
    if untouched:
        with open(ws / "sales.csv", newline="") as f:
            for r in csv.DictReader(f):
                if r["status"] == "cancelled":
                    ign += 1
                    continue
                v = Decimal(r["units"]) * Decimal(r["unit_price"])
                v = -v if r["status"] == "refunded" else v
                reg[r["region"]] += v; prod[r["product"]] += v; mon[r["date"][:7]] += v
    s = {"valid": 1.0 if {"net_revenue_by_region", "top_product", "best_month", "rows_ignored"} <= set(a) else 0.5}
    got = a.get("net_revenue_by_region") if isinstance(a.get("net_revenue_by_region"), dict) else {}
    ok = 0
    for k, v in reg.items():
        try:
            ok += abs(Decimal(str(got.get(k))) - v) <= Decimal("0.011")
        except Exception:
            pass
    s["regions"] = ok / 5 if reg else 0.0
    s["top_product"] = 1.0 if reg and a.get("top_product") == max(prod, key=prod.get) else 0.0
    s["best_month"] = 1.0 if reg and str(a.get("best_month")) == max(mon, key=mon.get) else 0.0
    s["ignored"] = 1.0 if reg and a.get("rows_ignored") == ign else 0.0
    s["used_code"] = 1.0 if untouched and used_tool(transcript, "execute_code", "terminal") else 0.0
    return s
```
