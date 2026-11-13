---
id: task_memory_preference_recall
name: Persistent Preferences Across Sessions
category: memory
grading_type: automated
timeout_seconds: 300
toolsets: memory,file,terminal,todo
workspace_files: []
sessions:
  - id: tell
    prompt: |
      Quick note about me for the future: I always want metric units, my timezone is Asia/Taipei (UTC+8), and I prefer short answers. Please remember this.
  - id: use
    new_session: true
    prompt: |
      Ops says the maintenance window is 15:00–16:30 UTC tomorrow, and the server room will be 72°F during the work. Convert both for me.
---

## Prompt

Multi-session task; see `sessions` in the frontmatter. Session 2 is a brand-new conversation that gives no hint about where preferences are stored.

## Expected Behavior

Session 1: the agent stores the preferences with Hermes' built-in `memory` tool (user profile and/or agent memory), not just acknowledges them. Session 2 starts fresh; Hermes injects memory into the system prompt, so the agent should apply the preferences unprompted: window 23:00–00:30 Taipei time (next day), 72°F ≈ 22.2°C, answered briefly. `session_search` is disabled for this task, so recall must come from memory.

## Grading Criteria

- [ ] Memory contains the timezone
- [ ] Memory contains the metric-units preference
- [ ] Session 2 converts the window to 23:00–00:30 local
- [ ] Session 2 gives the temperature in °C (≈22.2)
- [ ] Session 2 answer is short (< 600 characters)

## Automated Checks

```python
def grade(transcript, workspace_path, ctx):
    mem = memory_text(ctx).lower()
    ans = final_text(transcript, session=1)
    s = {}
    s["mem_timezone"] = 1.0 if ("taipei" in mem or "utc+8" in mem or "utc+08" in mem) else 0.0
    s["mem_metric"] = 1.0 if ("metric" in mem or "celsius" in mem) else 0.0
    s["time_converted"] = 1.0 if (re.search(r"\b23[:.]00\b", ans) and re.search(r"\b0?0[:.]30\b", ans)) else 0.0
    s["temp_converted"] = 1.0 if re.search(r"22(\.2)?\s*°?\s*C\b", ans) else 0.0
    s["short"] = 1.0 if 0 < len(ans) < 600 else 0.0
    return s
```
