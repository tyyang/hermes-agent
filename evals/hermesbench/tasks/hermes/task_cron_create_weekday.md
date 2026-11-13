---
id: task_cron_create_weekday
name: Natural-Language Schedule to Cron Job
category: scheduling
grading_type: automated
timeout_seconds: 180
toolsets: cronjob,file,terminal
workspace_files: []
---

## Prompt

Every weekday at 8:30 in the morning, have Hermes check https://status.example.com and send me a short summary of any open incidents. Name the job `morning-status`.

## Expected Behavior

The agent uses `cronjob_manage` (action create) — not the system crontab — with schedule `30 8 * * 1-5` (or an equivalent natural-language schedule Hermes parses to it), name `morning-status`, and a self-contained prompt that mentions the status URL (cron runs start without conversation context). It confirms the job and may note that the gateway must be running for jobs to fire.

## Grading Criteria

- [ ] Exactly one job named morning-status in Hermes' cron store
- [ ] Schedule is weekdays 08:30
- [ ] Job prompt is self-contained (mentions the status URL and incidents)
- [ ] Created with cronjob_manage, not system crontab

## Automated Checks

```python
def grade(transcript, workspace_path, ctx):
    jobs = [j for j in cron_jobs(ctx) if "morning-status" in str(j.get("name", ""))]
    j = jobs[0] if jobs else {}
    expr = normalize_cron(cron_expr(j))
    prompt = str(j.get("prompt", ""))
    crontab_used = any(c["name"] == "terminal" and "crontab" in json.dumps(c["arguments"]) for c in tool_calls(transcript))
    return {
        "job_exists": 1.0 if len(jobs) == 1 else (0.5 if jobs else 0.0),
        "schedule": 1.0 if expr in ("30 8 * * 1-5", "30 08 * * 1-5") else 0.0,
        "prompt_self_contained": 1.0 if "status.example.com" in prompt and re.search(r"incident", prompt, re.I) else 0.0,
        "native_tool": 1.0 if used_tool(transcript, "cronjob_manage") and not crontab_used else 0.0,
    }
```
