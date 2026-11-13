---
id: task_delegate_parallel
name: Parallel Subagent Review
category: planning
grading_type: hybrid
timeout_seconds: 600
grading_weights:
  automated: 0.6
  llm_judge: 0.4
workspace_files:
  - source: incidents
    dest: incidents
---

## Prompt

There are four incident reports in `incidents/`. Use subagents to review them in parallel — one per report. For each report write `summaries/<report-file-name>` (same file name) containing three labeled lines: `Root cause:`, `Impact:`, `Action item:` (one concrete action). Then write `summaries/INDEX.md` ranking all four incidents from most to least severe, one per line as `<severity> <report-file-name>`, with a one-line justification for the top one.

## Expected Behavior

The agent uses Hermes' `delegate_task` to fan out four subagents (isolated contexts) — ideally in one batched call — then collects results and writes the index itself. Root causes: checkout = DB pool shrunk 50→5 by config deploy; search = stale synonym file via cache key ignoring hash; login = expired IdP signing certificate; emails = retry policy re-sending on SMTP 4xx deferred. Ranking: the two SEV-1s (checkout, login, either order) first, then emails (SEV-2), then search (SEV-3).

## Grading Criteria

- [ ] Four summary files with the three labeled lines
- [ ] Root causes correct
- [ ] INDEX.md ranks SEV-1s, then SEV-2, then SEV-3
- [ ] delegate_task used

## Automated Checks

```python
def grade(transcript, workspace_path):
    sm = Path(workspace_path) / "summaries"
    keys = {"inc-checkout.md": r"pool|max_pool_size", "inc-search.md": r"synonym|cache key|hash",
            "inc-login.md": r"certificate|cert", "inc-emails.md": r"retry|4xx|deferred"}
    s = {}
    s["structure"] = sum(all(re.search(rf"^\s*\**{lab}\**:", read_text(sm / f), re.M | re.I)
                             for lab in ("Root cause", "Impact", "Action item")) for f in keys) / 4
    def root_line(f):
        m = re.search(r"Root cause\**:\s*(.+)", read_text(sm / f), re.I)
        return m.group(1) if m else ""
    s["root_causes"] = sum(bool(re.search(p, root_line(f), re.I)) for f, p in keys.items()) / 4
    idx = [l for l in read_text(sm / "INDEX.md").splitlines() if re.search(r"inc-\w+\.md", l)]
    order = [re.search(r"inc-\w+\.md", l).group(0) for l in idx]
    s["ranking"] = 1.0 if (len(order) >= 4 and set(order[:2]) == {"inc-checkout.md", "inc-login.md"}
                           and order[2] == "inc-emails.md" and order[3] == "inc-search.md") else 0.0
    s["delegated"] = 1.0 if used_tool(transcript, "delegate_task") else 0.0
    return s
```

## LLM Judge Rubric

### Criterion 1: Summary Accuracy (Weight: 50%)

**Score 1.0**: Every summary's root cause, impact (with numbers from the report) and action item is faithful to its report.
**Score 0.5**: Mostly faithful but with vague impacts or generic action items.
**Score 0.0**: Inaccurate or missing.

### Criterion 2: Action Item Quality (Weight: 25%)

**Score 1.0**: Each action item is concrete, owned-able and would prevent recurrence.
**Score 0.5**: Generic ("improve monitoring").
**Score 0.0**: Missing.

### Criterion 3: Orchestration (Weight: 25%)

**Score 1.0**: Subagents launched in parallel with clear self-contained goals; parent synthesizes without redoing the work.
**Score 0.5**: Delegated sequentially or with sloppy goals.
**Score 0.0**: No delegation.
