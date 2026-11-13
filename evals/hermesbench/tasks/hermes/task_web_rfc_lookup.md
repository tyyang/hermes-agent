---
id: task_web_rfc_lookup
name: Web Lookup with Verification
category: research
grading_type: automated
timeout_seconds: 240
requires: [web]
workspace_files: []
---

## Prompt

Use web search to verify (don't rely on memory) the current IETF RFC numbers for: (1) HTTP Semantics, (2) HTTP/3, (3) QUIC: A UDP-Based Multiplexed and Secure Transport. Write `rfcs.json` as an object mapping `"http_semantics"`, `"http3"` and `"quic_transport"` to objects with `"rfc"` (integer) and `"published"` (`YYYY-MM`), plus a `"sources"` array of the URLs you used.

## Expected Behavior

The agent uses `web_search` and/or `web_extract` (or the browser) to confirm: HTTP Semantics = RFC 9110 (2022-06), HTTP/3 = RFC 9114 (2022-06), QUIC transport = RFC 9000 (2021-05). It cites rfc-editor.org / datatracker / similar pages. Answering from memory without any web tool call loses the verification point even if correct.

## Grading Criteria

- [ ] rfcs.json valid with the required shape
- [ ] HTTP Semantics → 9110, 2022-06
- [ ] HTTP/3 → 9114, 2022-06
- [ ] QUIC → 9000, 2021-05
- [ ] At least one source URL listed
- [ ] A web tool was actually used

## Automated Checks

```python
def grade(transcript, workspace_path):
    d = load_json(Path(workspace_path) / "rfcs.json")
    keys = ["valid", "http_semantics", "http3", "quic", "sources", "web_used"]
    if not isinstance(d, dict):
        return {k: 0.0 for k in keys}
    def check(key, rfc, pub):
        e = d.get(key) if isinstance(d.get(key), dict) else {}
        return 0.5 * (e.get("rfc") == rfc) + 0.5 * (str(e.get("published", ""))[:7] == pub)
    s = {"valid": 1.0 if all(isinstance(d.get(k), dict) for k in ("http_semantics", "http3", "quic_transport")) else 0.0}
    s["http_semantics"] = check("http_semantics", 9110, "2022-06")
    s["http3"] = check("http3", 9114, "2022-06")
    s["quic"] = check("quic_transport", 9000, "2021-05")
    srcs = d.get("sources") if isinstance(d.get("sources"), list) else []
    s["sources"] = 1.0 if any(str(u).startswith("http") for u in srcs) else 0.0
    s["web_used"] = 1.0 if used_tool(transcript, "web_search", "web_extract", "browser_exec") else 0.0
    return s
```
