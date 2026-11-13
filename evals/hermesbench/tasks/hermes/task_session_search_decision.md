---
id: task_session_search_decision
name: Recall a Past Decision (session_search)
category: session_recall
grading_type: automated
timeout_seconds: 300
toolsets: session_search,file,terminal
hermes_config:
  memory:
    memory_enabled: false
    user_profile_enabled: false
workspace_files: []
sessions:
  - id: decide
    prompt: |
      Let's lock in the database for project Orion. We compared MySQL 8 and PostgreSQL 16 and we're going with PostgreSQL 16, mainly because we need logical replication into the analytics cluster. Hosting budget is capped at $1,200/month. Just confirm back in one line, no files needed.
  - id: unrelated
    new_session: true
    prompt: |
      Suggest one name for a Slack channel used for on-call handoffs. Just the name.
  - id: recall
    new_session: true
    prompt: |
      In an earlier conversation we settled the database for project Orion. Which database and version did we pick, why, and what was the monthly budget cap?
---

## Prompt

Multi-session task; see `sessions` in the frontmatter. The memory tool is disabled for this task.

## Expected Behavior

With memory off, the only way to answer session 3 is Hermes' `session_search` over the session history (FTS5 + summarization). The agent should search, find the Orion conversation and answer: PostgreSQL 16, for logical replication to the analytics cluster, budget $1,200/month. It should not guess.

## Grading Criteria

- [ ] session_search called in the final session
- [ ] Database and version correct
- [ ] Reason (logical replication) correct
- [ ] Budget cap correct

## Automated Checks

```python
def grade(transcript, workspace_path):
    ans = final_text(transcript, session=2)
    return {
        "searched": 1.0 if used_tool(transcript, "session_search", session=2) else 0.0,
        "database": 1.0 if re.search(r"postgres(ql)?\s*16", ans, re.I) else 0.0,
        "reason": 1.0 if re.search(r"logical replication", ans, re.I) else 0.0,
        "budget": 1.0 if re.search(r"1,?200", ans) else 0.0,
    }
```
