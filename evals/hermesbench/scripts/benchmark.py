#!/usr/bin/env python3
"""HermesBench: PinchBench's 147 tasks + Hermes-specific tasks, run through the real `hermes` CLI.

Examples
  python scripts/benchmark.py --model anthropic/claude-sonnet-4.5 --provider openrouter          # everything
  python scripts/benchmark.py --model ... --suite pinchbench        # the 147 PinchBench tasks only
  python scripts/benchmark.py --model ... --suite pinchbench-core   # PinchBench's own core subset
  python scripts/benchmark.py --model ... --suite hermes            # Hermes-specific tasks only
  python scripts/benchmark.py --model ... --suite task_sanity,task_memory_preference_recall
  python scripts/benchmark.py --model ... --skip-requires browser,vision,fws --no-judge
"""

from __future__ import annotations

import argparse
import json
import re
import logging
import statistics
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))

from lib_grading import DEFAULT_JUDGE_MODEL, JudgeCache, grade_task  # noqa: E402
from lib_hermes import execute_task, prune_hermes_home  # noqa: E402
from lib_tasks import SUITES, Task, TaskLoader  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
logger = logging.getLogger("hermesbench")
PASS_THRESHOLD = 0.8


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Run HermesBench against a Hermes Agent install.")
    p.add_argument("--model", required=True, help="Model passed to `hermes chat -m`")
    p.add_argument("--provider", default=None, help="Provider passed to `hermes chat --provider` (default: auto)")
    p.add_argument("--hermes-cmd", default="hermes",
                   help="How to invoke Hermes, e.g. 'hermes' or '/path/.venv/bin/python -m hermes_cli.main'")
    p.add_argument("--hermes-home-template", default=str(Path.home() / ".hermes"),
                   help="Home whose config.yaml/.env/auth.json seed every task's isolated HERMES_HOME")
    p.add_argument("--suite", default="all",
                   help="all | pinchbench | hermes | core | pinchbench-core | hermes-core | automated-only "
                        "| comma-separated task ids")
    p.add_argument("--category", default=None,
                   help="Only run these categories (comma-separated; `logs_analysis` or `pinchbench/log_analysis`)")
    p.add_argument("--skip-requires", default="",
                   help="Skip tasks needing these capabilities: web,browser,vision,image_gen,fws")
    p.add_argument("--runs", type=int, default=1, help="Runs per task (scores are averaged)")
    p.add_argument("--timeout-multiplier", type=float, default=1.0)
    p.add_argument("--reasoning", default=None, help="Passed to `hermes chat --reasoning`")
    p.add_argument("--judge", default=DEFAULT_JUDGE_MODEL,
                   help="Judge model, PinchBench syntax: openrouter/..., anthropic/..., openai/..., kilo/..., claude "
                        "(default: PinchBench's default judge)")
    p.add_argument("--no-fail-fast", action="store_true",
                   help="Keep going even if task_sanity scores 0 (PinchBench aborts the run)")
    p.add_argument("--no-judge", action="store_true", help="Skip LLM judging (hybrid tasks use automated part)")
    p.add_argument("--keep-runtime", action="store_true",
                   help="Keep each task's HERMES_HOME installs/ and cache/ (~1.2 GB/task) after grading")
    p.add_argument("--output-dir", default=str(ROOT / "results"))
    p.add_argument("--list", action="store_true", help="List the selected tasks and exit")
    p.add_argument("-v", "--verbose", action="store_true")
    return p.parse_args(argv)


def select_tasks(loader: TaskLoader, tasks: List[Task], args: argparse.Namespace) -> List[Task]:
    suite = args.suite
    core = set(loader.core())
    if suite == "all":
        chosen = tasks
    elif suite in SUITES:
        chosen = [t for t in tasks if t.suite == suite]
    elif suite == "core":
        chosen = [t for t in tasks if t.task_id in core]
    elif suite.endswith("-core") and suite[:-5] in SUITES:
        chosen = [t for t in tasks if t.suite == suite[:-5] and t.task_id in core]
    elif suite == "automated-only":
        chosen = [t for t in tasks if t.grading_type == "automated"]
    else:
        ids = {s.strip() for s in suite.split(",") if s.strip()}
        unknown = ids - {t.task_id for t in tasks}
        if unknown:
            raise SystemExit(f"unknown task ids: {sorted(unknown)}")
        chosen = [t for t in tasks if t.task_id in ids]
    if args.category:
        cats = {c.strip() for c in args.category.split(",")}
        chosen = [t for t in chosen if t.category in cats or t.qualified_category in cats]
    return chosen


def _rollup(rows: List[Dict[str, Any]], category_order: List[str]) -> Dict[str, Any]:
    """PinchBench aggregation: every task is worth 1.0; score = earned / possible; per-category the same."""
    cats: Dict[str, Dict[str, Any]] = {}
    for c in category_order:
        v = [r["mean"] for r in rows if r["qualified_category"] == c]
        if v:
            cats[c] = {"score": round(sum(v), 6), "max_score": float(len(v)),
                       "pct": round(100 * sum(v) / len(v), 1), "task_count": len(v)}
    earned, possible = sum(r["mean"] for r in rows), float(len(rows))
    return {"score_pct": round(100 * earned / possible, 1) if possible else 0.0, "earned": round(earned, 4),
            "possible": possible, "category_scores": cats}


def summarize(results: List[Dict[str, Any]], category_order: List[str]) -> Dict[str, Any]:
    scored = [r for r in results if not r.get("skipped")]
    out: Dict[str, Any] = {"overall": _rollup(scored, category_order), "suites": {}}
    for suite in SUITES:
        rows = [r for r in scored if r["suite"] == suite]
        if rows or any(r["suite"] == suite for r in results):
            out["suites"][suite] = _rollup(rows, category_order)
            out["suites"][suite]["tasks_scored"] = len(rows)
            out["suites"][suite]["tasks_skipped"] = sum(1 for r in results if r["suite"] == suite and r.get("skipped"))
    means = [r["mean"] for r in scored]
    tok = sum(r["usage"]["total_tokens"] for r in scored)
    out.update({
        "pass_rate_pct": round(100 * sum(m >= PASS_THRESHOLD for m in means) / len(means), 1) if means else 0.0,
        "tasks_scored": len(scored), "tasks_skipped": len(results) - len(scored),
        "efficiency": {
            "total_tokens": tok,
            "total_tool_calls": sum(r["tool_calls"] for r in scored),
            "total_tool_errors": sum(r["tool_errors"] for r in scored),
            "total_wall_seconds": round(sum(r["execution_time"] for r in scored), 1),
            "score_per_1k_tokens": round(sum(means) / (tok / 1000), 6) if tok else None,  # PinchBench metric
        },
    })
    return out


def write_markdown(path: Path, meta: Dict[str, Any], summary: Dict[str, Any], results: List[Dict[str, Any]]) -> None:
    eff = summary["efficiency"]
    lines = [f"# HermesBench — {meta['model']}", ""]
    for suite, s in summary["suites"].items():
        label = {"pinchbench": "PinchBench tasks", "hermes": "Hermes tasks"}.get(suite, suite)
        lines.append(f"- {label}: **{s['score_pct']}%** ({s['earned']:.2f} / {s['possible']:.0f})"
                     f"  ·  skipped: {s['tasks_skipped']}")
    o = summary["overall"]
    lines += [f"- All scored tasks: {o['score_pct']}% ({o['earned']:.2f} / {o['possible']:.0f})"
              f"  ·  pass rate (≥{PASS_THRESHOLD}): {summary['pass_rate_pct']}%  ·  runs/task: {meta['runs']}",
              f"- Tokens: {eff['total_tokens']:,}  ·  tool calls: {eff['total_tool_calls']}"
              f"  ·  tool errors: {eff['total_tool_errors']}  ·  wall: {eff['total_wall_seconds']}s"
              f"  ·  judge: {meta['judge'] or 'off'}", "",
              "| Category | Score | Tasks |", "|---|---:|---:|"]
    lines += [f"| {c} | {v['pct']}% ({v['score']:.2f}/{v['max_score']:.0f}) | {v['task_count']} |"
              for c, v in o["category_scores"].items()]
    lines += ["", "| Task | Category | Score | ±std | Tokens | Tools | Status |", "|---|---|---:|---:|---:|---:|---|"]
    for r in results:
        if r.get("skipped"):
            lines.append(f"| {r['task_id']} | {r['qualified_category']} | – | – | – | – | skipped ({r['skipped']}) |")
        else:
            lines.append(f"| {r['task_id']} | {r['qualified_category']} | {r['mean']:.2f} | {r['std']:.2f} | "
                         f"{r['usage']['total_tokens']:,} | {r['tool_calls']} | {','.join(sorted(set(r['statuses'])))} |")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO, format="%(message)s")
    loader = TaskLoader(ROOT / "tasks", ROOT / "assets")
    tasks = select_tasks(loader, loader.load_all(), args)
    if args.list:
        for t in tasks:
            extra = ",".join(t.requires) + (f"  [{'; '.join(t.patches)}]" if t.patches else "")
            print(f"{t.task_id:42s} {t.qualified_category:30s} {t.grading_type:10s} {extra}")
        print(f"{len(tasks)} tasks")
        return 0

    skip_caps = {s.strip() for s in args.skip_requires.split(",") if s.strip()}
    template = Path(args.hermes_home_template).expanduser()
    template = template if template.exists() else None
    if template is None:
        logger.warning("No Hermes home template found; tasks run with an empty config (set --hermes-home-template).")
    run_id = time.strftime("%Y%m%d-%H%M%S") + "-" + re.sub(r"[^A-Za-z0-9._-]", "_", args.model)  # no ":" in paths
    out_dir = Path(args.output_dir) / run_id
    out_dir.mkdir(parents=True, exist_ok=True)
    cache = JudgeCache(Path(args.output_dir) / ".judge_cache.json")
    judge = None if args.no_judge else args.judge

    results: List[Dict[str, Any]] = []
    for n, task in enumerate(tasks, 1):
        missing = sorted(set(task.requires) & skip_caps)
        base = {"task_id": task.task_id, "suite": task.suite, "category": task.category,
                "qualified_category": task.qualified_category, "grading_type": task.grading_type,
                "patches": task.patches}
        if missing:
            logger.info("[%d/%d] %s — skipped (requires %s)", n, len(tasks), task.task_id, ",".join(missing))
            results.append({**base, "skipped": "requires " + ",".join(missing)})
            continue
        runs = []
        for k in range(args.runs):
            logger.info("[%d/%d] %s (run %d/%d)", n, len(tasks), task.task_id, k + 1, args.runs)
            run_dir = out_dir / task.task_id / f"run{k + 1}"
            try:
                ex = execute_task(task, run_dir=run_dir, hermes_cmd=args.hermes_cmd,
                                  model=args.model, provider=args.provider, template_home=template,
                                  timeout_multiplier=args.timeout_multiplier, reasoning=args.reasoning)
            except RuntimeError as exc:
                logger.error("   %s", exc)
                if "not found" in str(exc):
                    return 2
                ex = {"status": "error", "workspace": "", "hermes_home": "", "transcript": [], "sessions": [],
                      "usage": {"total_tokens": 0}, "tool_calls": 0, "tool_errors": 0, "execution_time": 0.0}
            g = grade_task(task, ex, judge, cache)
            logger.info("   score=%.2f status=%s tokens=%s tools=%s %s", g.score, ex["status"],
                        ex["usage"].get("total_tokens"), ex["tool_calls"], g.notes[:120])
            run_dir.mkdir(parents=True, exist_ok=True)
            (run_dir / "grade.json").write_text(json.dumps(g.to_dict(), indent=2), encoding="utf-8")
            if ex["hermes_home"] and not args.keep_runtime:
                prune_hermes_home(Path(ex["hermes_home"]))
            runs.append({"grade": g.to_dict(), "status": ex["status"], "usage": ex["usage"],
                         "tool_calls": ex["tool_calls"], "tool_errors": ex["tool_errors"],
                         "execution_time": ex["execution_time"]})
        scores = [r["grade"]["score"] for r in runs]
        results.append({**base, "mean": statistics.mean(scores), "std": statistics.pstdev(scores) if len(scores) > 1 else 0.0,
                        "runs": runs, "statuses": [r["status"] for r in runs],
                        "usage": {"total_tokens": int(statistics.mean(r["usage"].get("total_tokens", 0) for r in runs))},
                        "tool_calls": round(statistics.mean(r["tool_calls"] for r in runs), 1),
                        "tool_errors": round(statistics.mean(r["tool_errors"] for r in runs), 1),
                        "execution_time": round(statistics.mean(r["execution_time"] for r in runs), 1)})
        if task.task_id == "task_sanity" and results[-1]["mean"] == 0.0 and not args.no_fail_fast:
            logger.error("FAIL FAST: task_sanity scored 0%% — aborting (PinchBench behavior; --no-fail-fast to continue)")
            return 3

    summary = summarize(results, loader.category_order())
    meta = {"benchmark": "hermesbench", "version": (ROOT / "BENCHMARK_VERSION").read_text().strip(),
            "model": args.model, "provider": args.provider, "judge": judge, "runs": args.runs, "suite": args.suite,
            "run_id": run_id, "timestamp": time.time()}
    (out_dir / "results.json").write_text(json.dumps({"meta": meta, "summary": summary, "tasks": results},
                                                     indent=2, ensure_ascii=False), encoding="utf-8")
    write_markdown(out_dir / "summary.md", meta, summary, results)
    logger.info("\n%s", (out_dir / "summary.md").read_text(encoding="utf-8"))
    logger.info("Results: %s", out_dir)
    return 0


if __name__ == "__main__":
    sys.exit(main())
