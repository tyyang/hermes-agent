---
id: task_exact_output_format
name: Strict Output Spec
category: files_coding
grading_type: automated
timeout_seconds: 120
workspace_files:
  - path: "services.txt"
    content: |
      api-gateway   port=8080  replicas=3  owner=platform
      billing       port=9001  replicas=2  owner=payments
      search        port=9200  replicas=5  owner=discovery
      notifier      port=7000  replicas=1  owner=platform
      reports       port=8500  replicas=0  owner=analytics
---

## Prompt

Read `services.txt` and write `services.json` that follows this spec exactly:

- Top-level JSON object with exactly two keys: `"services"` and `"total_replicas"`.
- `"services"` is an array sorted by port ascending. Each element has exactly the keys `"name"` (string), `"port"` (integer) and `"owner"` (string).
- Exclude any service with 0 replicas.
- `"total_replicas"` is the integer sum of replicas of the included services.
- No other keys, no comments, valid JSON.

## Expected Behavior

The agent reads the file, parses the whitespace-separated key=value columns, drops `reports` (0 replicas), sorts the remaining four services by port (notifier 7000, api-gateway 8080, billing 9001, search 9200) and writes total_replicas = 11. Tests precise instruction following rather than reasoning depth.

## Grading Criteria

- [ ] services.json exists and is valid JSON
- [ ] Exactly the two top-level keys
- [ ] Zero-replica service excluded
- [ ] Sorted by port ascending
- [ ] Each element has exactly name/port/owner with correct types
- [ ] total_replicas is 11

## Automated Checks

```python
def grade(transcript, workspace_path):
    data = load_json(Path(workspace_path) / "services.json")
    keys = ["valid_json", "top_level_keys", "excluded_zero", "sorted", "element_shape", "total"]
    if not isinstance(data, dict):
        return {k: 0.0 for k in keys}
    s = {"valid_json": 1.0}
    s["top_level_keys"] = 1.0 if set(data) == {"services", "total_replicas"} else 0.0
    svcs = data.get("services") if isinstance(data.get("services"), list) else []
    names = [x.get("name") for x in svcs if isinstance(x, dict)]
    s["excluded_zero"] = 1.0 if names and "reports" not in names and len(names) == 4 else 0.0
    s["sorted"] = 1.0 if names == ["notifier", "api-gateway", "billing", "search"] else 0.0
    ok = bool(svcs) and all(isinstance(x, dict) and set(x) == {"name", "port", "owner"}
                            and isinstance(x["port"], int) and not isinstance(x["port"], bool)
                            and isinstance(x["name"], str) and isinstance(x["owner"], str) for x in svcs)
    s["element_shape"] = 1.0 if ok else 0.0
    s["total"] = 1.0 if data.get("total_replicas") == 11 and isinstance(data.get("total_replicas"), int) else 0.0
    return s
```
