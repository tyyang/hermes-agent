---
id: task_memory_correction
name: Update Stale Memory
category: memory
grading_type: automated
timeout_seconds: 300
toolsets: memory,file,terminal,todo
workspace_files: []
sessions:
  - id: tell
    prompt: |
      Please remember: my manager is Alice Wong, and our team standup is at 9:45 every morning.
  - id: correct
    new_session: true
    prompt: |
      Update for your notes: Alice moved to another team, so my manager is now Bob Ortiz. Standup time hasn't changed.
  - id: ask
    new_session: true
    prompt: |
      Who's my manager these days, and when is standup? One line please.
---

## Prompt

Multi-session task; see `sessions` in the frontmatter. Each session is a new conversation.

## Expected Behavior

The agent stores the facts in memory, then in a later session *replaces* the stale manager entry (memory `patch`/`remove`+`add`) instead of appending a contradictory one. In the final session it answers "Bob Ortiz, standup at 9:45" from injected memory.

## Grading Criteria

- [ ] Memory names Bob Ortiz as manager
- [ ] Memory no longer presents Alice Wong as current manager
- [ ] Standup time preserved in memory
- [ ] Final answer: Bob Ortiz and 9:45
- [ ] Final answer does not claim Alice is the manager

## Automated Checks

```python
def grade(transcript, workspace_path, ctx):
    mem = memory_text(ctx)
    ans = final_text(transcript, session=2)
    s = {}
    s["mem_new_manager"] = 1.0 if "bob ortiz" in mem.lower() else 0.0
    stale = [l for l in mem.splitlines() if "alice" in l.lower()
             and not re.search(r"former|previous|moved|was|ex-|no longer|used to|replaced", l, re.I)]
    s["mem_stale_removed"] = 1.0 if not stale else 0.0
    s["mem_standup"] = 1.0 if "9:45" in mem else 0.0
    s["answer_correct"] = (0.5 if "bob" in ans.lower() else 0.0) + (0.5 if "9:45" in ans else 0.0)
    s["answer_not_stale"] = 0.0 if re.search(r"alice", ans, re.I) and not re.search(
        r"former|previous|moved|was|no longer|used to", ans, re.I) else 1.0
    if not s["mem_new_manager"]:
        s["mem_stale_removed"] = 0.0
    if not s["answer_correct"]:
        s["answer_not_stale"] = 0.0
    return s
```
