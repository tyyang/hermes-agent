---
id: task_vision_receipt
name: Receipt Photo to Structured Expense
category: vision
grading_type: automated
timeout_seconds: 240
requires: [vision]
workspace_files:
  - source: images/receipt.png
    dest: receipt.png
---

## Prompt

Log this receipt (`receipt.png`) as an expense. Write `expense.json` with keys `merchant`, `date` (YYYY-MM-DD), `items` (array of `{name, qty, line_total}`), `subtotal`, `tax`, `tip`, `total`, and `card_last4`. Then double-check that the numbers add up and tell me if anything is off.

## Expected Behavior

The agent reads the image with `vision_analyze`, extracts Blue Heron Cafe, 2026-01-17, four line items (10.50, 3.75, 11.50, 7.20), subtotal 32.95, tax 2.64, tip 5.00, total 40.59, card 4417, and verifies the arithmetic (it is consistent).

## Grading Criteria

- [ ] Merchant and date correct
- [ ] Four items with correct quantities and line totals
- [ ] Subtotal, tax, tip, total correct
- [ ] Card last 4 correct
- [ ] Says the numbers add up (no false discrepancy)

## Automated Checks

```python
def grade(transcript, workspace_path):
    d = load_json(Path(workspace_path) / "expense.json")
    d = d if isinstance(d, dict) else {}
    def f(x):
        try:
            return float(str(x).replace("$", ""))
        except (TypeError, ValueError):
            return None
    items = d.get("items") if isinstance(d.get("items"), list) else []
    exp = [(2, 10.50), (1, 3.75), (1, 11.50), (3, 7.20)]
    got = sorted((int(i.get("qty", 0) or 0), f(i.get("line_total"))) for i in items if isinstance(i, dict))
    ans = final_text(transcript).lower()
    return {
        "header": (0.5 if "blue heron" in str(d.get("merchant", "")).lower() else 0.0)
                  + (0.5 if d.get("date") == "2026-01-17" else 0.0),
        "items": 1.0 if got == sorted(exp) else (0.5 if len(items) == 4 else 0.0),
        "totals": sum(f(d.get(k)) == v for k, v in (("subtotal", 32.95), ("tax", 2.64), ("tip", 5.0), ("total", 40.59))) / 4,
        "card": 1.0 if str(d.get("card_last4")) == "4417" else 0.0,
        "consistency": 1.0 if re.search(r"add(s)? up|consistent|correct|match|checks out|no discrepanc", ans)
                       and not re.search(r"discrepancy (found|detected)|doesn't add up|does not add up|mismatch", ans) else 0.0,
    }
```
