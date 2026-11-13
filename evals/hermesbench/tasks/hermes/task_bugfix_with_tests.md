---
id: task_bugfix_with_tests
name: Fix Bugs Until Tests Pass
category: files_coding
grading_type: automated
timeout_seconds: 240
workspace_files:
  - source: bugfix/inventory.py
    dest: inventory.py
  - source: bugfix/test_inventory.py
    dest: test_inventory.py
---

## Prompt

The tests in `test_inventory.py` are failing. Fix the bugs in `inventory.py` so that all tests pass. Do not modify the test file. Run the tests to confirm before you finish.

## Expected Behavior

The agent runs the tests (terminal), reads `inventory.py`, and fixes four bugs with targeted edits (`patch` or `write_file`): `add` must accumulate, `count` of an unknown SKU returns 0, `total_value` treats unknown prices as 0, and `low_stock` is strictly-below and sorted. It re-runs the tests and reports success. The grader also runs hidden tests covering the same contract, so special-casing the visible tests fails.

## Grading Criteria

- [ ] Visible tests pass
- [ ] Hidden tests pass
- [ ] Test file left unmodified
- [ ] Agent ran the tests itself (terminal / execute_code)

## Automated Checks

```python
def grade(transcript, workspace_path):
    import shutil, subprocess, sys, tempfile
    ws = Path(workspace_path)
    s = {}
    hidden = '''
import unittest
from inventory import Inventory, OutOfStock
class Hidden(unittest.TestCase):
    def test_remove_then_count(self):
        i = Inventory(); i.add("a", 4); i.add("a", 1); i.remove("a", 2)
        self.assertEqual(i.count("a"), 3)
    def test_add_rejects_nonpositive(self):
        with self.assertRaises(ValueError):
            Inventory().add("a", 0)
    def test_remove_unknown_raises(self):
        with self.assertRaises(OutOfStock):
            Inventory().remove("zzz", 1)
    def test_value_rounding(self):
        i = Inventory(); i.add("x", 3); i.add("y", 1)
        self.assertEqual(i.total_value({"x": 0.1, "y": 0.2}), 0.5)
    def test_low_stock_sorted(self):
        i = Inventory()
        for sku, q in [("m", 1), ("b", 2), ("z", 0 + 1), ("c", 9)]:
            i.add(sku, q)
        self.assertEqual(i.low_stock(3), ["b", "m", "z"])
        self.assertEqual(i.low_stock(1), [])
'''
    def run(test_module, extra=None):
        with tempfile.TemporaryDirectory() as d:
            for f in ("inventory.py", "test_inventory.py"):
                if (ws / f).exists():
                    shutil.copy(ws / f, d)
            if extra:
                Path(d, "test_hidden.py").write_text(extra)
            try:
                p = subprocess.run([sys.executable, "-m", "unittest", "-q", test_module], cwd=d,
                                   capture_output=True, text=True, timeout=60)
                return p.returncode == 0
            except Exception:
                return False
    s["visible_tests"] = 1.0 if run("test_inventory") else 0.0
    s["hidden_tests"] = 1.0 if run("test_hidden", hidden) else 0.0
    s["tests_untouched"] = 1.0 if file_sha(ws / "test_inventory.py") == \
        "8249bdf5ecb2104a9730b0a891828a3d25e7938e5931d6563b13b4e255b78f91" else 0.0
    ran = any(c["name"] in ("terminal", "execute_code") and "test" in json.dumps(c["arguments"])
              for c in tool_calls(transcript))
    s["ran_tests"] = 1.0 if ran else 0.0
    return s
```
