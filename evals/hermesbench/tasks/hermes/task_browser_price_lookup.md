---
id: task_browser_price_lookup
name: Browser Navigation and Lookup
category: browser
grading_type: automated
timeout_seconds: 240
requires: [browser]
toolsets: browser,file,terminal
workspace_files: []
---

## Prompt

Using your browser tools, open https://books.toscrape.com , find the book "Sharp Objects", and tell me its listed price and whether it is in stock. Also save them to `book.json` as `{"title": ..., "price_gbp": <number>, "in_stock": <bool>}`.

## Expected Behavior

The agent drives the browser (`browser_exec` / CDP tools), finds the product page and reports £47.82, in stock. The task runs with `-t browser,file,terminal`, so `web_extract` is not available and the browser must be used. (Oracle shared with hermes-agent `evals/browser_use/tasks/easy.json`.)

## Grading Criteria

- [ ] book.json is valid with the three keys
- [ ] Price 47.82
- [ ] in_stock is true
- [ ] Final answer states the price
- [ ] Browser tool used

## Automated Checks

```python
def grade(transcript, workspace_path):
    d = load_json(Path(workspace_path) / "book.json")
    d = d if isinstance(d, dict) else {}
    s = {"valid": 1.0 if {"title", "price_gbp", "in_stock"} <= set(d) else 0.0}
    try:
        s["price"] = 1.0 if abs(float(d.get("price_gbp")) - 47.82) < 0.005 else 0.0
    except (TypeError, ValueError):
        s["price"] = 0.0
    s["in_stock"] = 1.0 if d.get("in_stock") is True else 0.0
    s["answer"] = 1.0 if "47.82" in final_text(transcript) else 0.0
    s["browser_used"] = 1.0 if any(c["name"].startswith("browser") for c in tool_calls(transcript)) else 0.0
    return s
```
