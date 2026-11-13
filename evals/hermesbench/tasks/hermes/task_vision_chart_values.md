---
id: task_vision_chart_values
name: Read Values from a Chart Image
category: vision
grading_type: automated
timeout_seconds: 240
requires: [vision]
workspace_files:
  - source: images/tickets_chart.png
    dest: tickets_chart.png
---

## Prompt

`tickets_chart.png` is a bar chart from a slide. Extract the data into `tickets.json` as `{"Q1": n, "Q2": n, "Q3": n, "Q4": n}`, and in your final answer tell me the yearly total and which quarter-over-quarter change was the largest increase (as a percentage, 1 decimal).

## Expected Behavior

The agent uses `vision_analyze` on the image (or a multimodal read), extracts 42/67/55/88, computes total 252 and the largest increase Q3→Q4 (+60.0%; Q1→Q2 is +59.5%, a deliberate near-tie that rewards doing the arithmetic rather than eyeballing).

## Grading Criteria

- [ ] tickets.json values all correct
- [ ] Total 252 stated
- [ ] Largest increase identified as Q3→Q4
- [ ] Percentage 60.0% stated
- [ ] Vision tool used

## Automated Checks

```python
def grade(transcript, workspace_path):
    d = load_json(Path(workspace_path) / "tickets.json")
    d = d if isinstance(d, dict) else {}
    ans = final_text(transcript)
    exp = {"Q1": 42, "Q2": 67, "Q3": 55, "Q4": 88}
    return {
        "values": sum(d.get(k) == v for k, v in exp.items()) / 4,
        "total": 1.0 if re.search(r"\b252\b", ans) else 0.0,
        "largest_change": 1.0 if re.search(r"Q3\s*(→|->|to|–|-)\s*Q4", ans) else 0.0,
        "percent": 1.0 if re.search(r"60(\.0)?\s*%", ans) else 0.0,
        "vision_used": 1.0 if used_tool(transcript, "vision_analyze", "read_file") else 0.0,
    }
```
