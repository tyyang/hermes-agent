---
id: task_session_search_detail
name: Recall Details from a Deleted Artifact
category: session_recall
grading_type: automated
timeout_seconds: 360
toolsets: session_search,file,terminal
hermes_config:
  memory:
    memory_enabled: false
    user_profile_enabled: false
workspace_files:
  - path: "app.log"
    content: |
      2026-03-02 10:14:55 INFO  worker-3 starting batch 8812
      2026-03-02 10:14:56 INFO  worker-3 loaded 412 invoices
      2026-03-02 10:14:58 ERROR worker-3 unhandled exception [code=E-4471]
      Traceback (most recent call last):
        File "/srv/app/billing/runner.py", line 41, in run_batch
          totals = build_invoice(row)
        File "/srv/app/billing/invoice.py", line 88, in build_invoice
          tenant = row["tenant_id"]
      KeyError: 'tenant_id'
      2026-03-02 10:14:58 WARN  worker-3 batch 8812 aborted, 0/412 committed
sessions:
  - id: inspect
    prompt: |
      Look at app.log and tell me briefly what's failing.
  - id: cleanup
    prompt: |
      Thanks. I've archived it elsewhere — please delete app.log from this folder.
  - id: recall
    new_session: true
    prompt: |
      A while ago you looked at a crash log for me (it's been deleted since, so don't look for it). What was the error code, the exception, and which file and line raised it?
---

## Prompt

Multi-session task; see `sessions` in the frontmatter. The memory tool is disabled for this task.

## Expected Behavior

Session 1 reads the log and diagnoses a `KeyError: 'tenant_id'` raised at `billing/invoice.py` line 88 (code E-4471). Session 1 continues and deletes the file. Session 3 is a fresh conversation; with the file gone and memory off, the agent must use `session_search` to recover the details.

## Grading Criteria

- [ ] app.log deleted
- [ ] session_search used in the final session
- [ ] Error code E-4471
- [ ] KeyError tenant_id
- [ ] billing/invoice.py line 88

## Automated Checks

```python
def grade(transcript, workspace_path):
    ans = final_text(transcript, session=2)
    return {
        "deleted": 0.0 if (Path(workspace_path) / "app.log").exists() else 1.0,
        "searched": 1.0 if used_tool(transcript, "session_search", session=2) else 0.0,
        "code": 1.0 if "E-4471" in ans else 0.0,
        "exception": 1.0 if re.search(r"KeyError", ans) and "tenant_id" in ans else 0.0,
        "location": 1.0 if "invoice.py" in ans and re.search(r"\b88\b", ans) else 0.0,
    }
```
