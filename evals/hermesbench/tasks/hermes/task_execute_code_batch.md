---
id: task_execute_code_batch
name: Batch Processing in Few Steps
category: data_processing
grading_type: automated
timeout_seconds: 300
workspace_files:
  - source: orders
    dest: orders
---

## Prompt

`orders/` holds 60 order JSON files. Produce `orders_report.json` with:

- `"by_status"`: count of orders per status
- `"repeat_customers"`: sorted list of customers with more than 8 orders
- `"shipped_revenue"`: total of `qty * price` over all items of shipped orders, rounded to 2 decimals
- `"largest_order"`: id of the order with the highest total (any status)

Be efficient about it.

## Expected Behavior

Reading 60 files one by one wastes dozens of tool calls and context. The efficient path is one `execute_code` script (Hermes' programmatic tool calling) or one terminal Python command. The grader recomputes the answer and awards an efficiency point for finishing in ≤ 8 tool calls.

## Grading Criteria

- [ ] by_status correct
- [ ] repeat_customers correct
- [ ] shipped_revenue correct
- [ ] largest_order correct
- [ ] Efficient: ≤ 8 tool calls total

## Automated Checks

```python
def grade(transcript, workspace_path):
    from collections import Counter
    from decimal import Decimal
    ws = Path(workspace_path)
    orders = [load_json(p) for p in sorted((ws / "orders").glob("*.json"))]
    orders = [o for o in orders if isinstance(o, dict)]
    st = Counter(o["status"] for o in orders)
    cust = Counter(o["customer"] for o in orders)
    tot = {o["id"]: sum(Decimal(str(i["qty"])) * Decimal(str(i["price"])) for i in o["items"]) for o in orders}
    shipped = sum((tot[o["id"]] for o in orders if o["status"] == "shipped"), Decimal(0))
    r = load_json(ws / "orders_report.json")
    r = r if isinstance(r, dict) else {}
    s = {}
    s["by_status"] = 1.0 if r.get("by_status") == dict(st) else 0.0
    s["repeat_customers"] = 1.0 if r.get("repeat_customers") == sorted(c for c, n in cust.items() if n > 8) else 0.0
    try:
        s["shipped_revenue"] = 1.0 if abs(Decimal(str(r.get("shipped_revenue"))) - shipped) <= Decimal("0.011") else 0.0
    except Exception:
        s["shipped_revenue"] = 0.0
    s["largest_order"] = 1.0 if r.get("largest_order") == max(tot, key=tot.get) else 0.0
    n = len(tool_calls(transcript))
    s["efficient"] = 1.0 if 0 < n <= 8 else (0.5 if 0 < n <= 15 else 0.0)
    return s
```
