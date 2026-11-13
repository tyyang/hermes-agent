---
id: task_browser_multi_page
name: Multi-Page Crawl and Aggregate
category: browser
grading_type: automated
timeout_seconds: 420
requires: [browser]
toolsets: browser,file,terminal,code_execution
workspace_files: []
---

## Prompt

Using your browser tools, open https://books.toscrape.com , go to the "Mystery" category, and go through ALL of its pages. Count how many Mystery books cost less than £30.00 and identify the single cheapest Mystery book. Write `mystery.json` as `{"under_30": <int>, "cheapest_title": ..., "cheapest_price_gbp": <number>}` and summarize in your final answer.

## Expected Behavior

The agent paginates through the category (2 pages), collects every price, and answers 19 books under £30, cheapest "Tastes Like Fear" at £10.69. Efficient agents extract a whole page per browser step (e.g. a `browser_exec` script) instead of clicking item by item. (Oracle from hermes-agent `evals/browser_use/tasks/hard.json`.)

## Grading Criteria

- [ ] mystery.json valid
- [ ] under_30 = 19
- [ ] Cheapest title correct
- [ ] Cheapest price 10.69
- [ ] Browser tool used

## Automated Checks

```python
def grade(transcript, workspace_path):
    d = load_json(Path(workspace_path) / "mystery.json")
    d = d if isinstance(d, dict) else {}
    s = {"valid": 1.0 if {"under_30", "cheapest_title", "cheapest_price_gbp"} <= set(d) else 0.0}
    s["count"] = 1.0 if d.get("under_30") == 19 else 0.0
    s["title"] = 1.0 if "tastes like fear" in str(d.get("cheapest_title", "")).lower() else 0.0
    try:
        s["price"] = 1.0 if abs(float(d.get("cheapest_price_gbp")) - 10.69) < 0.005 else 0.0
    except (TypeError, ValueError):
        s["price"] = 0.0
    s["browser_used"] = 1.0 if any(c["name"].startswith("browser") for c in tool_calls(transcript)) else 0.0
    return s
```
