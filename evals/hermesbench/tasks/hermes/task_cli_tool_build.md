---
id: task_cli_tool_build
name: Build a Small CLI Tool
category: files_coding
grading_type: automated
timeout_seconds: 240
workspace_files:
  - path: "sample.txt"
    content: |
      The quick brown fox. The lazy dog!
      the fox, the DOG, and THE cat.
---

## Prompt

Write a Python 3 command-line script `wordfreq.py` (standard library only) with this interface:

```
python3 wordfreq.py FILE [--top N] [--ignore-case] [--min-length L]
```

- Words are maximal runs of letters `[A-Za-z]+`; everything else is a separator.
- Without `--ignore-case`, counting is case-sensitive. With it, words are lowercased first.
- `--min-length L` drops words shorter than L characters (default 1).
- Output the top N words (default 10), one per line, formatted as `word<TAB>count`, sorted by count descending, then by word ascending (plain string order) for ties.
- If FILE does not exist, print an error to stderr and exit with status 2.

Test it on `sample.txt` before you finish.

## Expected Behavior

The agent writes the script with argparse/re/collections, runs it on the sample (e.g. `--ignore-case --top 3` should print `the\t5`, then `dog\t2` and `fox\t2`), and fixes any issues. The grader executes the script against hidden inputs and edge cases.

## Grading Criteria

- [ ] Script exists and runs
- [ ] Default case-sensitive counting and tie ordering correct
- [ ] --ignore-case correct
- [ ] --top and --min-length correct
- [ ] Missing file → stderr message and exit code 2
- [ ] Agent executed the script itself

## Automated Checks

```python
def grade(transcript, workspace_path):
    import subprocess, sys, tempfile
    from collections import Counter
    ws = Path(workspace_path)
    script = ws / "wordfreq.py"
    keys = ["runs", "case_sensitive", "ignore_case", "top_minlen", "missing_file", "self_tested"]
    if not script.exists():
        return {k: 0.0 for k in keys}
    text = "Zeta beta Beta alpha, beta; ALPHA alpha zeta-zeta x y  y x\nGamma gamma GAMMA delta"
    tmp = Path(tempfile.mkdtemp()) / "in.txt"
    tmp.write_text(text)

    def expected(ignore=False, top=10, minlen=1):
        words = re.findall(r"[A-Za-z]+", text)
        if ignore:
            words = [w.lower() for w in words]
        c = Counter(w for w in words if len(w) >= minlen)
        return [f"{w}\t{n}" for w, n in sorted(c.items(), key=lambda kv: (-kv[1], kv[0]))[:top]]

    def run(*args):
        try:
            p = subprocess.run([sys.executable, str(script), *args], capture_output=True, text=True, timeout=20)
            return p.returncode, [l.rstrip("\r") for l in p.stdout.strip().splitlines()], p.stderr
        except Exception:
            return -1, [], ""
    s = {}
    rc, out, _ = run(str(tmp))
    s["runs"] = 1.0 if rc == 0 and out else 0.0
    s["case_sensitive"] = 1.0 if out == expected() else 0.0
    rc, out, _ = run(str(tmp), "--ignore-case")
    s["ignore_case"] = 1.0 if out == expected(ignore=True) else 0.0
    rc1, out1, _ = run(str(tmp), "--top", "3", "--ignore-case")
    rc2, out2, _ = run(str(tmp), "--min-length", "5")
    s["top_minlen"] = (0.5 if out1 == expected(True, 3) else 0.0) + (0.5 if out2 == expected(minlen=5) else 0.0)
    rc, out, err = run(str(tmp) + ".missing")
    s["missing_file"] = 1.0 if rc == 2 and err.strip() else 0.0
    s["self_tested"] = 1.0 if any(c["name"] in ("terminal", "execute_code") and "wordfreq" in json.dumps(c["arguments"])
                                  for c in tool_calls(transcript)) else 0.0
    return s
```
