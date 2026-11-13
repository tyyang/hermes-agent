---
id: task_cron_manage
name: Edit and Remove Scheduled Jobs
category: scheduling
grading_type: automated
timeout_seconds: 300
toolsets: cronjob,file,terminal
workspace_files: []
sessions:
  - id: create
    prompt: |
      Set up two scheduled jobs: `plant-reminder` that reminds me to water the plants every Monday and Thursday at 9am, and `weekly-review` that every Friday at 4pm summarizes the git log of ~/projects/app for the week.
  - id: modify
    new_session: true
    prompt: |
      Change of plans: delete the plant reminder, and move the weekly review to 5pm (still Fridays). Leave everything else as is.
---

## Prompt

Multi-session task; see `sessions` in the frontmatter. Session 2 is a new conversation, so the agent must list existing jobs to find them.

## Expected Behavior

Session 1 creates two jobs via `cronjob_manage` (`0 9 * * 1,4` and `0 16 * * 5`). Session 2 lists jobs, removes `plant-reminder`, and updates `weekly-review` to `0 17 * * 5` in place (update, not delete-and-recreate with a different prompt).

## Grading Criteria

- [ ] plant-reminder removed
- [ ] weekly-review exists exactly once
- [ ] weekly-review schedule is Fridays 17:00
- [ ] weekly-review prompt still about the git log summary
- [ ] Session 2 listed jobs before changing them

## Automated Checks

```python
def grade(transcript, workspace_path, ctx):
    jobs = cron_jobs(ctx)
    plant = [j for j in jobs if "plant" in str(j.get("name", "")).lower()]
    review = [j for j in jobs if "weekly-review" in str(j.get("name", ""))]
    j = review[0] if review else {}
    listed = any(c["name"] == "cronjob_manage" and c["arguments"].get("action") == "list"
                 for c in tool_calls(transcript, session=1))
    return {
        "plant_removed": 1.0 if not plant and review else 0.0,
        "review_once": 1.0 if len(review) == 1 else 0.0,
        "review_schedule": 1.0 if normalize_cron(cron_expr(j)) == "0 17 * * 5" else 0.0,
        "review_prompt": 1.0 if re.search(r"git", str(j.get("prompt", "")), re.I) else 0.0,
        "listed_first": 1.0 if listed else 0.0,
    }
```
