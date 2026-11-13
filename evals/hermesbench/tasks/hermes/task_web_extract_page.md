---
id: task_web_extract_page
name: Extract Structured Data from a Page
category: research
grading_type: automated
timeout_seconds: 240
requires: [web]
workspace_files: []
---

## Prompt

Fetch https://quotes.toscrape.com/tag/books/ and save every quote on that page to `quotes.json` as an array of objects with `"author"` and `"text"`. Then, in your final answer, tell me how many quotes are on the page and which authors appear more than once.

## Expected Behavior

The agent uses `web_extract` (or `browser_exec`/terminal curl) to read the tag page, parses all quotes, writes the JSON file and answers: 10 quotes; Mark Twain and Jane Austen each appear twice.

## Grading Criteria

- [ ] quotes.json is a JSON array of {author, text}
- [ ] It has 10 entries
- [ ] Mark Twain and Jane Austen each appear twice in the file
- [ ] Final answer states the count (10)
- [ ] Final answer names Mark Twain and Jane Austen

## Automated Checks

```python
def grade(transcript, workspace_path):
    from collections import Counter
    d = load_json(Path(workspace_path) / "quotes.json")
    ans = final_text(transcript)
    s = {}
    ok = isinstance(d, list) and d and all(isinstance(x, dict) and "author" in x and "text" in x for x in d)
    s["shape"] = 1.0 if ok else 0.0
    s["count_file"] = 1.0 if ok and len(d) == 10 else 0.0
    c = Counter(str(x.get("author", "")).strip() for x in d) if ok else Counter()
    s["repeat_authors_file"] = 1.0 if c.get("Mark Twain") == 2 and c.get("Jane Austen") == 2 else 0.0
    s["answer_count"] = 1.0 if re.search(r"\b10\b|\bten\b", ans, re.I) else 0.0
    s["answer_authors"] = 1.0 if "Mark Twain" in ans and "Jane Austen" in ans else 0.0
    return s
```
