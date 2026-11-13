---
id: task_codebase_search
name: Codebase Navigation with Decoys
category: files_coding
grading_type: automated
timeout_seconds: 180
workspace_files:
  - source: navrepo
    dest: repo
---

## Prompt

In the `repo/` monorepo, find the setting that caps the exponential backoff between HTTP retries in the code that is actually in use. Write `answer.json` with exactly these keys:

- `"file"`: path of the file that defines it, relative to `repo/`
- `"constant"`: the constant's name
- `"default_seconds"`: its default value as a number
- `"env_override"`: the environment variable that overrides it

## Expected Behavior

The agent searches the repo (`search_files` is ideal; terminal grep is fine) and distinguishes the live definition in `src/core/net/retry_policy.py` (`MAX_BACKOFF_SECONDS`, default 47.5, overridable by `HB_NET_MAX_BACKOFF`) from decoys: a deprecated doc in `docs/archive/` (120 / `RETRY_CAP`), an unused `legacy/net_v1/retry.py` (60), a CI file that sets the variable to 5, and an unrelated cache timeout of 30.

## Grading Criteria

- [ ] answer.json is valid JSON with the four keys
- [ ] Correct file
- [ ] Correct constant name
- [ ] Correct default (47.5), not a decoy value
- [ ] Correct env var

## Automated Checks

```python
def grade(transcript, workspace_path):
    a = load_json(Path(workspace_path) / "answer.json")
    keys = ["valid", "file", "constant", "default", "env"]
    if not isinstance(a, dict):
        return {k: 0.0 for k in keys}
    s = {"valid": 1.0 if {"file", "constant", "default_seconds", "env_override"} <= set(a) else 0.5}
    f = str(a.get("file", "")).replace("\\", "/").lstrip("./")
    s["file"] = 1.0 if f in ("src/core/net/retry_policy.py", "repo/src/core/net/retry_policy.py") else 0.0
    s["constant"] = 1.0 if a.get("constant") == "MAX_BACKOFF_SECONDS" else 0.0
    try:
        s["default"] = 1.0 if abs(float(a.get("default_seconds")) - 47.5) < 1e-9 else 0.0
    except (TypeError, ValueError):
        s["default"] = 0.0
    s["env"] = 1.0 if a.get("env_override") == "HB_NET_MAX_BACKOFF" else 0.0
    return s
```
