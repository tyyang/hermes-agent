---
id: task_rename_across_files
name: Precise Cross-File Rename
category: files_coding
grading_type: automated
timeout_seconds: 180
workspace_files:
  - source: rename/shop
    dest: shop
  - source: rename/README.md
    dest: README.md
---

## Prompt

In this repo, rename the function `get_usr` to `get_user` everywhere it is defined, imported, called, exported or documented. Do not rename anything else — in particular `get_usr_count` must keep its name.

## Expected Behavior

The agent searches the repo (`search_files` or terminal grep), then edits `shop/models.py`, `shop/__init__.py` (import and `__all__`), `shop/services.py`, `shop/api.py` (attribute access `models.get_usr`) and `README.md`. A blind `sed s/get_usr/get_user/g` also renames `get_usr_count` and is penalized. The grader imports the package with a check script.

## Grading Criteria

- [ ] No remaining `get_usr` identifier (word-bounded) in code or docs
- [ ] `get_usr_count` keeps its name and still works
- [ ] Package imports and behaves correctly (check script passes)
- [ ] `__all__` exports `get_user`
- [ ] README updated

## Automated Checks

```python
def grade(transcript, workspace_path):
    import subprocess, sys
    ws = Path(workspace_path)
    files = list((ws / "shop").glob("*.py")) + [ws / "README.md"]
    blob = "\n".join(read_text(f) for f in files)
    s = {}
    s["old_name_gone"] = 0.0 if re.search(r"\bget_usr\b", blob) else 1.0
    s["count_preserved"] = 1.0 if ("def get_usr_count" in read_text(ws / "shop/models.py")
                                   and "get_user_count" not in blob) else 0.0
    check = '''
from shop import get_user, get_usr_count
from shop.api import handle
assert get_user(1)["name"] == "Ada"
assert get_usr_count() == 2
assert handle(2)["discount"] == 0.1 and handle(2)["population"] == 2
print("OK")
'''
    try:
        p = subprocess.run([sys.executable, "-c", check], cwd=ws, capture_output=True, text=True, timeout=30)
        s["behaves"] = 1.0 if p.returncode == 0 and "OK" in p.stdout else 0.0
    except Exception:
        s["behaves"] = 0.0
    s["exported"] = 1.0 if re.search(r"__all__[^\n]*['\"]get_user['\"]", read_text(ws / "shop/__init__.py")) else 0.0
    s["readme"] = 1.0 if "get_user(" in read_text(ws / "README.md") and "get_usr_count" in read_text(ws / "README.md") else 0.0
    return s
```
