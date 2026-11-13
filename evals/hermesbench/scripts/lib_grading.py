"""Grading for HermesBench. Scoring is PinchBench's, unchanged.

* automated: the `grade(...)` function in a task's `## Automated Checks` block is exec'd and the task
  score is the plain mean of the numeric values it returns (PinchBench `_average_scores`, no clamping).
  PinchBench graders run exactly as upstream: same namespace (incl. `_PINCHBENCH_PRIVATE_IMAGE_KEY_PATH`),
  same `grade(transcript, workspace_path)` call.
  HermesBench-suite graders may additionally take a third `ctx` argument (HERMES_HOME etc.), use the
  helpers below, and return `_weights` for a weighted mean.
* llm_judge: PinchBench's judge prompt, API dispatch, 2 attempts, response parser/normalizer; the
  score is the judge's `total` (the arithmetic mean of rubric criteria). Default judge:
  openrouter/anthropic/claude-haiku-4.5 (PinchBench default).
* hybrid: grading_weights mix (default 0.5/0.5), PinchBench `_combine_grades`.

pb_vendor.py holds the vendored PinchBench functions (MIT, github.com/pinchbench/skill @ 819384a).
"""

from __future__ import annotations

import hashlib
import inspect
import json
import logging
import os
import re
import time
import types
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import pb_vendor as pb
from lib_tasks import Task

logger = logging.getLogger("hermesbench")

DEFAULT_JUDGE_MODEL = pb.DEFAULT_JUDGE_MODEL


# --------------------------------------------------------------------------------------------
# Helpers injected into every automated grader's namespace
# --------------------------------------------------------------------------------------------

def tool_calls(transcript: List[Dict[str, Any]], session: Optional[int] = None) -> List[Dict[str, Any]]:
    """All tool calls as [{"name", "arguments", "session"}], optionally for one session index."""
    out = []
    for ev in transcript:
        if ev.get("type") != "message" or (session is not None and ev.get("session") != session):
            continue
        msg = ev.get("message", {})
        if msg.get("role") != "assistant":
            continue
        for item in msg.get("content", []):
            if item.get("type") == "toolCall":
                out.append({"name": item.get("name", ""), "arguments": item.get("arguments") or {},
                            "session": ev.get("session")})
    return out


def used_tool(transcript, *names: str, session: Optional[int] = None) -> bool:
    # Known limitation (README "Known grader false negatives"): only direct tool calls count. A tool
    # invoked from execute_code via `from hermes_tools import web_search` shows up as `execute_code`,
    # so web_used-style checks can miss it. Left unchanged to keep scores comparable across runs.
    wanted = set(names)
    return any(c["name"] in wanted for c in tool_calls(transcript, session))


def tool_args_text(transcript, *names: str, session: Optional[int] = None) -> str:
    """Concatenated JSON of the arguments of matching tool calls (all calls if no names)."""
    calls = [c for c in tool_calls(transcript, session) if not names or c["name"] in names]
    return "\n".join(json.dumps(c["arguments"], ensure_ascii=False) for c in calls)


def assistant_texts(transcript, session: Optional[int] = None) -> List[str]:
    out = []
    for ev in transcript:
        if ev.get("type") != "message" or (session is not None and ev.get("session") != session):
            continue
        msg = ev.get("message", {})
        if msg.get("role") == "assistant":
            out += [c.get("text", "") for c in msg.get("content", []) if c.get("type") == "text"]
    return out


def final_text(transcript, session: Optional[int] = None) -> str:
    """Last assistant text of the given session (default: the last session)."""
    if session is None:
        sessions = [ev.get("session") for ev in transcript if ev.get("type") == "message"]
        session = max((s for s in sessions if s is not None), default=None)
    texts = assistant_texts(transcript, session)
    return texts[-1] if texts else ""


def session_text(transcript, session: Optional[int] = None) -> str:
    return "\n".join(assistant_texts(transcript, session))


def read_text(path) -> str:
    try:
        return Path(path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def memory_text(ctx: Dict[str, Any]) -> str:
    """Contents of the Hermes built-in memory (MEMORY.md + USER.md) in the task's HERMES_HOME."""
    mem = Path(ctx.get("hermes_home", "")) / "memories"
    return "\n".join(read_text(p) for p in sorted(mem.glob("*.md"))) if mem.exists() else ""


def hermes_home_text(ctx: Dict[str, Any], max_bytes: int = 2_000_000) -> str:
    """Every readable text file under HERMES_HOME except the seeded secrets (.env/auth.json).
    Used by secret-hygiene checks."""
    home = Path(ctx.get("hermes_home", ""))
    chunks, total = [], 0
    if not home.exists():
        return ""
    for p in home.rglob("*"):
        if not p.is_file() or p.name in (".env", "auth.json"):
            continue
        try:
            data = p.read_bytes()[:max_bytes]
        except OSError:
            continue
        total += len(data)
        chunks.append(data.decode("utf-8", errors="replace"))
        if total > 50 * max_bytes:
            break
    return "\n".join(chunks)


def find_skills(ctx: Dict[str, Any]) -> Dict[str, Path]:
    """{skill_name: SKILL.md path} for every skill under HERMES_HOME/skills (name from frontmatter or dir)."""
    root = Path(ctx.get("hermes_home", "")) / "skills"
    out: Dict[str, Path] = {}
    if not root.exists():
        return out
    for p in root.rglob("SKILL.md"):
        name = p.parent.name
        m = re.search(r"^name:\s*['\"]?([^'\"\n]+)", read_text(p), re.MULTILINE)
        if m:
            name = m.group(1).strip()
        out[name] = p
        out.setdefault(p.parent.name, p)
    return out


def cron_jobs(ctx: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Jobs from HERMES_HOME/cron/jobs.json (tolerates list or {"jobs": [...]} shapes)."""
    p = Path(ctx.get("hermes_home", "")) / "cron" / "jobs.json"
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    if isinstance(data, dict):
        data = data.get("jobs", list(data.values()) if all(isinstance(v, dict) for v in data.values()) else [])
    return [j for j in data if isinstance(j, dict)]


def cron_expr(job: Dict[str, Any]) -> str:
    sched = job.get("schedule")
    if isinstance(sched, dict):
        return str(sched.get("expr") or sched.get("display") or sched.get("value") or "")
    return str(sched or job.get("schedule_display") or "")


def normalize_cron(expr: str) -> str:
    """Canonicalize weekday names so '30 8 * * MON-FRI' == '30 8 * * 1-5'."""
    e = " ".join(expr.lower().split())
    for i, d in enumerate(["sun", "mon", "tue", "wed", "thu", "fri", "sat"]):
        e = re.sub(rf"\b{d}\w*\b", str(i), e)
    return e


def file_sha(path) -> str:
    try:
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()
    except OSError:
        return ""


def load_json(path) -> Any:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def num_close(text: str, value: float, tol: float = 0.01) -> bool:
    """True if any number in *text* is within relative tolerance *tol* of *value*."""
    for m in re.finditer(r"-?\d[\d,]*\.?\d*", text or ""):
        try:
            x = float(m.group(0).replace(",", ""))
        except ValueError:
            continue
        if abs(x - value) <= max(abs(value) * tol, 1e-9):
            return True
    return False


GRADER_HELPERS = {
    "tool_calls": tool_calls, "used_tool": used_tool, "tool_args_text": tool_args_text,
    "assistant_texts": assistant_texts, "final_text": final_text, "session_text": session_text,
    "read_text": read_text, "memory_text": memory_text, "hermes_home_text": hermes_home_text,
    "find_skills": find_skills, "cron_jobs": cron_jobs, "cron_expr": cron_expr, "normalize_cron": normalize_cron,
    "file_sha": file_sha, "load_json": load_json, "num_close": num_close,
    "Path": Path, "re": re, "json": json, "os": os,
}



# --------------------------------------------------------------------------------------------
# Grade results
# --------------------------------------------------------------------------------------------

@dataclass
class GradeResult:
    task_id: str
    score: float
    grading_type: str
    breakdown: Dict[str, float] = field(default_factory=dict)
    notes: str = ""
    max_score: float = 1.0

    def to_dict(self) -> Dict[str, Any]:
        return {"task_id": self.task_id, "score": round(self.score, 4), "max_score": self.max_score,
                "grading_type": self.grading_type,
                "breakdown": {k: round(v, 4) for k, v in self.breakdown.items()}, "notes": self.notes}


def _stage_private_key(task: Task) -> str:
    """PinchBench copies assets/image_classification_answer_key.json to a private runtime path that the
    agent's workspace never sees, and exposes it to graders as _PINCHBENCH_PRIVATE_IMAGE_KEY_PATH."""
    src = task.assets_dir / pb._PRIVATE_IMAGE_KEY_FILENAME
    if not src.exists():
        return ""
    dest = pb._PRIVATE_IMAGE_KEY_RUNTIME_PATH
    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(src.read_bytes())
        os.chmod(dest, 0o600)
        return str(dest)
    except OSError as exc:
        logger.warning("failed to stage private image answer key: %s", exc)
        return ""


def grade_automated(task: Task, execution: Dict[str, Any]) -> GradeResult:
    code = pb._extract_grading_code(task)
    if not code:
        return GradeResult(task.task_id, 0.0, "automated", notes="No automated grading code found")
    ns: Dict[str, Any] = {}
    key = _stage_private_key(task)
    if key:
        ns["_PINCHBENCH_PRIVATE_IMAGE_KEY_PATH"] = key
    if task.suite != "pinchbench":
        ns.update(GRADER_HELPERS)
    try:
        exec(compile(code, str(task.file_path), "exec"), ns)
        fn = ns.get("grade")
        if not callable(fn):
            return GradeResult(task.task_id, 0.0, "automated", notes="Automated grading function missing")
        args = [execution.get("transcript", []), execution.get("workspace", "")]
        if len(inspect.signature(fn).parameters) >= 3:
            args.append({"hermes_home": execution.get("hermes_home", ""), "sessions": execution.get("sessions", []),
                         "usage": execution.get("usage", {}), "tool_calls": execution.get("tool_calls", 0),
                         "status": execution.get("status")})
        scores = fn(*args)
    except Exception as exc:  # upstream would abort the task; we score 0 and keep the run going
        logger.exception("grader for %s crashed", task.task_id)
        return GradeResult(task.task_id, 0.0, "automated", notes=f"grader error: {exc!r}")
    if not isinstance(scores, dict):
        scores = {}
    weights = scores.pop("_weights", None)
    breakdown = pb._normalize_score_dict(scores)
    if isinstance(weights, dict) and breakdown:  # HermesBench extension; PinchBench graders never set it
        tw = sum(float(weights.get(k, 1.0)) for k in breakdown)
        total = sum(v * float(weights.get(k, 1.0)) for k, v in breakdown.items()) / tw if tw else 0.0
    else:
        total = pb._average_scores(scores)
    return GradeResult(task.task_id, total, "automated", breakdown)


# --------------------------------------------------------------------------------------------
# LLM judge (PinchBench)
# --------------------------------------------------------------------------------------------

class JudgeCache:
    """Persistent cache keyed like PinchBench's (task|transcript|rubric|model|workspace)."""

    def __init__(self, path: Optional[Path]):
        self.path = path
        self.data: Dict[str, Any] = {}
        if path and path.exists():
            try:
                self.data = json.loads(path.read_text(encoding="utf-8"))
            except ValueError:
                self.data = {}

    def get(self, key: str) -> Optional[Dict[str, Any]]:
        return self.data.get(key)

    def put(self, key: str, value: Dict[str, Any]) -> None:
        self.data[key] = value
        if self.path:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(self.data, indent=2), encoding="utf-8")


def _judge_view(task: Task) -> Any:
    """PinchBench's prompt builder reads task.prompt; multi-session tasks show every session prompt."""
    if len(task.sessions) <= 1:
        return task
    prompt = "\n\n".join(f"(session {i + 1}{', new conversation' if s['new_session'] else ''})\n{s['prompt']}"
                          for i, s in enumerate(task.sessions))
    return types.SimpleNamespace(prompt=prompt, expected_behavior=task.expected_behavior)


def _call_judge(prompt: str, model: str, timeout: float) -> Dict[str, Any]:
    base = os.environ.get("HB_JUDGE_BASE_URL")
    if base:  # any OpenAI-compatible endpoint (HermesBench addition; same system message + payload)
        return pb._judge_via_openai_compat(prompt, model.split("/", 1)[-1] if model.startswith("openai/") else model,
                                           base.rstrip("/") + "/chat/completions",
                                           os.environ.get("HB_JUDGE_API_KEY", ""), timeout)
    return pb.call_judge_api(prompt=prompt, model=model, timeout_seconds=timeout)


def grade_llm_judge(task: Task, execution: Dict[str, Any], judge_model: Optional[str],
                    cache: Optional[JudgeCache] = None, timeout: float = 180.0) -> GradeResult:
    if not judge_model:
        return GradeResult(task.task_id, 0.0, "llm_judge", notes="judge disabled (--no-judge)")
    transcript = execution.get("transcript", [])
    status = execution.get("status", "unknown")
    if not transcript and status != "success":
        return GradeResult(task.task_id, 0.0, "llm_judge",
                           notes=f"Skipped: task execution failed ({status}), no transcript to evaluate")
    summary = pb._summarize_transcript(transcript)
    workspace_content = pb._read_workspace_files(execution.get("workspace", ""))
    rubric = task.llm_judge_rubric or pb._format_grading_criteria(task)
    key = hashlib.sha256(f"{task.task_id}|{summary}|{rubric}|{judge_model}|{workspace_content}".encode()).hexdigest()[:16]
    cached = cache.get(key) if cache else None
    if cached:
        return GradeResult(task.task_id, cached["score"], "llm_judge", cached.get("breakdown", {}),
                           cached.get("notes", "") + " [cached]")
    prompt = pb._build_judge_prompt(_judge_view(task), summary, rubric, workspace_content)
    raw: Dict[str, Any] = {}
    for attempt in range(2):
        res = _call_judge(prompt, judge_model, timeout)
        if res.get("status") != "success":
            logger.warning("judge call failed (attempt %d/2): %s", attempt + 1, res.get("error", res.get("status")))
            if attempt < 1:
                time.sleep(2 ** attempt)
                continue
        raw = pb._parse_judge_text(res.get("text", ""))
        break
    parsed = pb._normalize_judge_response(raw)
    total, notes = parsed.get("total"), parsed.get("notes", "")
    if not raw:
        notes = "LLM judge failed: no parseable response after all attempts"
    elif total is None:
        notes = "LLM judge failed: response parsed but no score extracted"
    result = GradeResult(task.task_id, float(total) if total is not None else 0.0, "llm_judge",
                         pb._normalize_score_dict(parsed.get("scores", {})), str(notes or ""))
    if total is not None and cache:
        cache.put(key, {"score": result.score, "breakdown": result.breakdown, "notes": result.notes})
    return result


def grade_task(task: Task, execution: Dict[str, Any], judge_model: Optional[str],
               cache: Optional[JudgeCache] = None) -> GradeResult:
    gt = task.grading_type
    if gt == "automated":
        return grade_automated(task, execution)
    if gt == "llm_judge":
        return grade_llm_judge(task, execution, judge_model, cache)
    if gt == "hybrid":
        a = grade_automated(task, execution)
        if not judge_model:  # --no-judge: hybrid tasks report their automated part only
            a.grading_type, a.notes = "hybrid(auto-only)", (a.notes + " judge disabled").strip()
            return a
        j = grade_llm_judge(task, execution, judge_model, cache)
        w = task.grading_weights or {"automated": 0.5, "llm_judge": 0.5}
        wa, wj = float(w.get("automated", 0.5)), float(w.get("llm_judge", 0.5))
        if wa + wj <= 0:
            wa = wj = 0.5
        total = (a.score * wa + j.score * wj) / (wa + wj)
        bd = {**{f"automated.{k}": v for k, v in a.breakdown.items()},
              **{f"llm_judge.{k}": v for k, v in j.breakdown.items()}}
        return GradeResult(task.task_id, total, "hybrid", bd, " | ".join(x for x in (a.notes, j.notes) if x))
    raise ValueError(f"Unknown grading type: {gt}")
