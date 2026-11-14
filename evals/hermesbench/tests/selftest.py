#!/usr/bin/env python3
"""Grader self-test.

hermes suite: every automated grader must (1) not crash and score <= 0.35 on an empty run,
(2) score ~1.0 on its golden reference solution (tests/golden.py), (3) stay under a ceiling on traps.
pinchbench suite: graders are upstream's, unchanged; every one must load, run on an empty run without
crashing, and every workspace asset must exist. Empty-run scores are reported, not enforced.

    python tests/selftest.py            # all tasks
    python tests/selftest.py task_git_rescue
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "tests"))

from golden import SOLVERS, TRAPS  # noqa: E402
from lib_grading import grade_automated  # noqa: E402
from lib_hermes import prepare_hermes_home, prepare_workspace, prune_hermes_home  # noqa: E402
from lib_tasks import TaskLoader  # noqa: E402

EMPTY_MAX = 0.35  # an agent that does nothing must not pass


def check_pinchbench(t) -> int:
    with tempfile.TemporaryDirectory() as d:
        run = Path(d)
        try:
            ws = prepare_workspace(t, run, t.assets_dir)
        except Exception as exc:
            print(f"FAIL  {t.task_id:38s} workspace setup: {exc!r}")
            return 1
        if t.grading_type == "llm_judge":
            print(f"OK    {t.task_id:38s} (llm_judge; assets ok)")
            return 0
        g = grade_automated(t, {"transcript": [], "workspace": str(ws), "status": "success"})
    bad = "grader error" in g.notes or "missing" in g.notes or "No automated" in g.notes
    flag = "  (empty run scores > 0.35 upstream)" if g.score > EMPTY_MAX else ""
    print(f"{'FAIL' if bad else 'OK  '}  {t.task_id:38s} empty={g.score:.2f} {g.notes}{flag}")
    return int(bad)


def check_prune() -> int:
    """prune_hermes_home drops only the dependency runtime; task output under cache/ survives."""
    with tempfile.TemporaryDirectory() as d:
        home = Path(d)
        gone = ["installs/env/bin/python", "cache/uv/wheel", "cache/pnpm/store"]
        kept = ["cache/terminal-output/out-1.log", "cache/scratch/a.txt", "cache/images/x.png",
                "memories/MEMORY.md", "skills/s/SKILL.md", "config.yaml"]
        for rel in gone + kept:
            (home / rel).parent.mkdir(parents=True, exist_ok=True)
            (home / rel).write_text("x")
        prune_hermes_home(home)
        bad = [r for r in gone if (home / r).exists()] + [r for r in kept if not (home / r).exists()]
    print(f"{'FAIL' if bad else 'OK  '}  {'prune_hermes_home':38s} {bad or ''}")
    return int(bool(bad))


def main() -> int:
    only = set(sys.argv[1:])
    tasks = [t for t in TaskLoader(ROOT / "tasks", ROOT / "assets").load_all() if not only or t.task_id in only]
    failures = 0 if only else check_prune()
    for t in tasks:
        if t.suite == "pinchbench":
            failures += check_pinchbench(t)
            continue
        if t.grading_type == "llm_judge":
            print(f"SKIP  {t.task_id:38s} (llm_judge only)")
            continue
        results = {}
        name = t.task_id.removeprefix("task_")
        for mode in ("empty", "golden", "trap"):
            if (mode == "golden" and name not in SOLVERS) or (mode == "trap" and name not in TRAPS):
                continue
            with tempfile.TemporaryDirectory() as d:
                run = Path(d)
                ws = prepare_workspace(t, run, t.assets_dir)
                home = prepare_hermes_home(t, run, t.assets_dir, None)
                transcript = (SOLVERS[name](ws, home) if mode == "golden"
                              else TRAPS[name][0](ws, home) if mode == "trap" else [])
                g = grade_automated(t, {"transcript": transcript, "workspace": str(ws), "hermes_home": str(home),
                                        "sessions": [], "usage": {}, "tool_calls": 0})
                results[mode] = g
        e, gd = results["empty"], results.get("golden")
        ok_empty = e.score <= EMPTY_MAX and "error" not in e.notes
        ok_golden = gd is None or gd.score >= 0.999
        tr = results.get("trap")
        ok_trap = tr is None or tr.score <= TRAPS[name][1]
        status = "OK  " if ok_empty and ok_golden and ok_trap else "FAIL"
        failures += status == "FAIL"
        gtxt = f"golden={gd.score:.2f}" if gd else "golden=n/a "
        ttxt = f" trap={tr.score:.2f}" if tr else ""
        print(f"{status}  {t.task_id:38s} empty={e.score:.2f} {gtxt}{ttxt} {e.notes}")
        if gd and not ok_golden:
            print("        golden breakdown:", {k: v for k, v in gd.breakdown.items() if v < 1}, gd.notes)
        if not ok_empty:
            print("        empty breakdown:", {k: v for k, v in e.breakdown.items() if v > 0})
    print(f"\n{len(tasks)} tasks checked, {failures} failing")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
