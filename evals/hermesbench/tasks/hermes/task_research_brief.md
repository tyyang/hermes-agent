---
id: task_research_brief
name: Sourced Technical Research Brief
category: research
grading_type: hybrid
timeout_seconds: 420
requires: [web]
grading_weights:
  automated: 0.4
  llm_judge: 0.6
workspace_files: []
---

## Prompt

I need to add local full-text search to a desktop app (single user, ~2 million short documents, must run offline, Python backend). Research these three options: SQLite FTS5, Tantivy (via its Python bindings), and Meilisearch. Write `search_brief.md` with: a comparison table (deployment model, index size/perf characteristics, ranking features, Python integration, license), a recommendation for my case with reasoning, and a "Sources" section listing at least 4 URLs you actually consulted.

## Expected Behavior

The agent runs several `web_search` / `web_extract` calls (possibly via `delegate_task` subagents in parallel), reads primary sources (sqlite.org FTS5 docs, tantivy / tantivy-py repos, Meilisearch docs), and writes a brief that is accurate: FTS5 is embedded in SQLite (public domain) with BM25 ranking; Tantivy is an embedded Rust library (MIT) with Python bindings; Meilisearch is a separate server process (MIT, with enterprise features under a different license). A reasonable recommendation for offline single-user desktop favors an embedded engine (FTS5 or Tantivy) over running a server.

## Grading Criteria

- [ ] search_brief.md exists
- [ ] All three options covered
- [ ] Contains a markdown comparison table
- [ ] Contains a clear recommendation
- [ ] At least 4 source URLs
- [ ] Web tools were used

## Automated Checks

```python
def grade(transcript, workspace_path):
    t = read_text(Path(workspace_path) / "search_brief.md")
    low = t.lower()
    s = {"exists": 1.0 if len(t) > 300 else 0.0}
    s["coverage"] = sum(x in low for x in ("fts5", "tantivy", "meilisearch")) / 3
    s["table"] = 1.0 if re.search(r"^\|.+\|\s*$\n^\|[\s:|-]+\|\s*$", t, re.M) else 0.0
    s["recommendation"] = 1.0 if re.search(r"recommend", low) else 0.0
    urls = set(re.findall(r"https?://[^\s)\]>]+", t))
    s["sources"] = min(len(urls) / 4, 1.0)
    s["web_used"] = 1.0 if used_tool(transcript, "web_search", "web_extract", "browser_exec") else 0.0
    return s
```

## LLM Judge Rubric

### Criterion 1: Technical Accuracy (Weight: 40%)

**Score 1.0**: Claims about each engine (embedding vs server, ranking, licensing, Python integration) are correct and specific.
**Score 0.75**: Mostly correct with one minor inaccuracy.
**Score 0.5**: Several vague or partly wrong claims.
**Score 0.25**: Major factual errors (e.g. calls Meilisearch embedded, wrong licenses).
**Score 0.0**: Mostly wrong or missing.

### Criterion 2: Recommendation Quality (Weight: 30%)

**Score 1.0**: Recommendation follows from the user's constraints (offline, single-user desktop, 2M docs, Python) and names trade-offs.
**Score 0.5**: Recommendation present but generic or weakly justified.
**Score 0.0**: No recommendation or it ignores the constraints.

### Criterion 3: Sourcing (Weight: 20%)

**Score 1.0**: Sources are primary/authoritative and match claims; transcript shows they were actually consulted.
**Score 0.5**: Some sources are secondary or not clearly used.
**Score 0.0**: Sources missing or fabricated (not visited in the transcript).

### Criterion 4: Clarity (Weight: 10%)

**Score 1.0**: Concise, well-structured, easy to act on.
**Score 0.5**: Readable but padded or disorganized.
**Score 0.0**: Hard to use.
