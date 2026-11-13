---
id: task_browser_login_flow
name: Login, Navigate, Extract
category: browser
grading_type: automated
timeout_seconds: 360
requires: [browser]
toolsets: browser,file,terminal
workspace_files: []
---

## Prompt

Using your browser: (1) log in at https://quotes.toscrape.com/login with username `admin` and password `admin` and confirm the login worked; (2) then go to the tag page for the tag "books" and report how many quotes are shown there and which authors appear more than once. Save `{"logged_in": true/false, "quote_count": <int>, "repeat_authors": [...]}` to `books_tag.json`.

## Expected Behavior

The agent fills and submits the login form (the nav link changes to "Logout"), navigates to the tag page, and reports 10 quotes with Mark Twain and Jane Austen appearing twice. (Oracle from hermes-agent `evals/browser_use/tasks/hard.json`.)

## Grading Criteria

- [ ] books_tag.json valid
- [ ] logged_in true and login evidenced in the transcript (Logout seen)
- [ ] quote_count = 10
- [ ] Repeat authors are exactly Mark Twain and Jane Austen
- [ ] Browser tool used

## Automated Checks

```python
def grade(transcript, workspace_path):
    d = load_json(Path(workspace_path) / "books_tag.json")
    d = d if isinstance(d, dict) else {}
    s = {"valid": 1.0 if {"logged_in", "quote_count", "repeat_authors"} <= set(d) else 0.0}
    results = " ".join(c.get("text", "") for e in transcript if e.get("type") == "message"
                       and e["message"].get("role") == "toolResult" for c in e["message"].get("content", []))
    s["login"] = 1.0 if d.get("logged_in") is True and "logout" in results.lower() else (0.5 if d.get("logged_in") is True else 0.0)
    s["count"] = 1.0 if d.get("quote_count") == 10 else 0.0
    ra = {str(x).strip() for x in d.get("repeat_authors") or []}
    s["authors"] = 1.0 if ra == {"Mark Twain", "Jane Austen"} else 0.0
    s["browser_used"] = 1.0 if any(c["name"].startswith("browser") for c in tool_calls(transcript)) else 0.0
    return s
```
