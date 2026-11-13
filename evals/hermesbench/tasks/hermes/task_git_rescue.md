---
id: task_git_rescue
name: Git Rescue on a Live Repo
category: files_coding
grading_type: automated
timeout_seconds: 180
workspace_files: []
setup:
  - git init -q -b main app && cd app && git config user.email bench@example.com && git config user.name Bench
  - cd app && echo "v1" > app.txt && git add . && git commit -qm "initial app"
  - cd app && echo "docs" > README.md && git add . && git commit -qm "add readme"
  - cd app && echo "login fix part 1" > login.py && git add . && git commit -qm "WIP login fix 1"
  - cd app && echo "login fix part 2" >> login.py && git add . && git commit -qm "WIP login fix 2"
  - cd app && echo "scratch notes, do not commit" > notes.tmp
---

## Prompt

In the git repo `app/`, I accidentally made my last 2 commits on `main`; they belong on a new branch named `feature/login-fix`. They have not been pushed. Fix the repo: the two commits should live on `feature/login-fix`, and `main` should point at the commit right before them ("add readme"). Leave `main` checked out when you're done. There's an untracked `notes.tmp` in there — don't lose it and don't commit it.

## Expected Behavior

The agent inspects the repo (`git log`, `git status`) via the terminal, creates the branch at the current HEAD (`git branch feature/login-fix`), resets main back two commits (`git reset --hard HEAD~2` is safe here because the only untracked file is left alone by reset), and verifies. It must not use destructive cleanup such as `git clean -fd` that would delete `notes.tmp`.

## Grading Criteria

- [ ] Branch `feature/login-fix` exists
- [ ] It contains both WIP commits on top of "add readme"
- [ ] `main` points at "add readme"
- [ ] `main` is checked out
- [ ] `notes.tmp` still exists and is untracked
- [ ] No other stray commits or tracked changes

## Automated Checks

```python
def grade(transcript, workspace_path):
    import subprocess
    repo = Path(workspace_path) / "app"
    def git(*a):
        p = subprocess.run(["git", *a], cwd=repo, capture_output=True, text=True)
        return p.stdout.strip() if p.returncode == 0 else None
    keys = ["branch_exists", "commits_on_branch", "main_reset", "main_checked_out", "notes_kept", "clean"]
    if not (repo / ".git").exists():
        return {k: 0.0 for k in keys}
    s = {}
    fb = git("rev-parse", "--verify", "refs/heads/feature/login-fix")
    s["branch_exists"] = 1.0 if fb else 0.0
    log_fb = git("log", "--format=%s", "feature/login-fix") or ""
    s["commits_on_branch"] = 1.0 if log_fb.splitlines()[:4] == ["WIP login fix 2", "WIP login fix 1", "add readme", "initial app"] else 0.0
    s["main_reset"] = 1.0 if (git("log", "-1", "--format=%s", "main") == "add readme"
                              and git("rev-list", "--count", "main") == "2") else 0.0
    s["main_checked_out"] = 1.0 if git("rev-parse", "--abbrev-ref", "HEAD") == "main" else 0.0
    status = git("status", "--porcelain") or ""
    s["notes_kept"] = 1.0 if (repo / "notes.tmp").exists() and "?? notes.tmp" in status else 0.0
    other = [l for l in status.splitlines() if l.strip() and "notes.tmp" not in l]
    s["clean"] = 1.0 if not other and "notes.tmp" not in (git("ls-files") or "") else 0.0
    if not fb:  # preservation checks only count once the actual fix was attempted
        s["main_checked_out"] = s["notes_kept"] = s["clean"] = 0.0
    return s
```
