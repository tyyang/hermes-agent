"""Vendored, unmodified grading/judge functions from PinchBench (github.com/pinchbench/skill, MIT,
commit 819384a). HermesBench grades every task through these so scores match PinchBench exactly.
Do not edit by hand; regenerate from upstream instead.

One local deviation from upstream: `_judge_via_openai_compat` reads `max_completion_tokens` from
HB_JUDGE_MAX_TOKENS (default 2048, upstream's value) so reasoning judges are not cut off."""
from __future__ import annotations

import json
import logging
import os
import re
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib import error, request

logger = logging.getLogger("pinchbench")
Task = Any  # PinchBench Task type, only used in annotations

DEFAULT_JUDGE_MODEL = "openrouter/anthropic/claude-haiku-4.5"


_PRIVATE_IMAGE_KEY_FILENAME = "image_classification_answer_key.json"


_PRIVATE_IMAGE_KEY_RUNTIME_PATH = (
    Path("/tmp/pinchbench/judge/private") / _PRIVATE_IMAGE_KEY_FILENAME
)


def _build_automated_namespace(skill_dir: Optional[Path]) -> Dict[str, Any]:
    namespace: Dict[str, Any] = {}
    private_key_path = _stage_private_image_key(skill_dir)
    if private_key_path:
        namespace["_PINCHBENCH_PRIVATE_IMAGE_KEY_PATH"] = private_key_path
    return namespace


def _stage_private_image_key(skill_dir: Optional[Path]) -> str:
    if skill_dir is None:
        return ""
    source_key_path = skill_dir / "assets" / _PRIVATE_IMAGE_KEY_FILENAME
    if not source_key_path.exists():
        return ""

    try:
        _PRIVATE_IMAGE_KEY_RUNTIME_PATH.parent.mkdir(parents=True, exist_ok=True)
        _PRIVATE_IMAGE_KEY_RUNTIME_PATH.write_bytes(source_key_path.read_bytes())
        os.chmod(_PRIVATE_IMAGE_KEY_RUNTIME_PATH, 0o600)
        return str(_PRIVATE_IMAGE_KEY_RUNTIME_PATH)
    except OSError as exc:
        logger.warning("Failed to stage private image answer key: %s", exc)
        return ""


def _extract_grading_code(task: Task) -> str:
    if not task.automated_checks:
        return ""
    match = re.search(r"```python\s*(.*?)\s*```", task.automated_checks, re.DOTALL)
    if not match:
        return ""
    return match.group(1)


def _average_scores(scores: Dict[str, Any]) -> float:
    values = [float(v) for v in scores.values() if isinstance(v, (int, float))]
    if not values:
        return 0.0
    return sum(values) / len(values)


def _normalize_score_dict(scores: Dict[str, Any]) -> Dict[str, float]:
    normalized: Dict[str, float] = {}
    for key, value in scores.items():
        try:
            normalized[str(key)] = float(value)
        except (TypeError, ValueError):
            continue
    return normalized


def _format_grading_criteria(task: Task) -> str:
    if not task.grading_criteria:
        return ""
    return "\n".join(f"- {criterion}" for criterion in task.grading_criteria)


def _summarize_transcript(transcript: List[Dict[str, Any]]) -> str:
    summary_parts: List[str] = []
    for event in transcript:
        if event.get("type") != "message":
            continue
        msg = event.get("message", {})
        role = msg.get("role")
        if role == "assistant":
            for item in msg.get("content", []):
                if item.get("type") == "toolCall":
                    args = item.get("arguments", {})
                    truncated_args: Dict[str, Any] = {}
                    for k, v in args.items():
                        if isinstance(v, str) and len(v) > 200:
                            truncated_args[k] = v[:200] + "...[truncated]"
                        else:
                            truncated_args[k] = v
                    summary_parts.append(f"Tool: {item.get('name')}({json.dumps(truncated_args)})")
                elif item.get("type") == "text":
                    text = item.get("text", "").strip()
                    if text:
                        summary_parts.append(f"Assistant: {text[:2000]}")
        elif role == "toolResult":
            content = msg.get("content", [])
            if content:
                result_preview = str(content[0])[:200]
                summary_parts.append(f"Result: {result_preview}")
        elif role == "user":
            content = msg.get("content", [])
            if content:
                summary_parts.append(f"User: {content[0]}")
    return "\n".join(summary_parts)


def _read_workspace_files(workspace_path: str) -> str:
    """Read user-created text files from workspace to provide grading context."""
    if not workspace_path:
        return ""
    workspace = Path(workspace_path)
    if not workspace.exists():
        return ""
    skip_names = {
        "BOOTSTRAP.md",
        "SOUL.md",
        "USER.md",
        "IDENTITY.md",
        "HEARTBEAT.md",
        "TOOLS.md",
        "AGENTS.md",
    }
    skip_dirs = {".git", ".openclaw", "__pycache__", "node_modules", "skills"}
    file_contents: List[str] = []
    for f in sorted(workspace.rglob("*")):
        if not f.is_file():
            continue
        rel = f.relative_to(workspace)
        parts = rel.parts
        if any(part.startswith(".") or part in skip_dirs for part in parts):
            continue
        if f.name in skip_names:
            continue
        try:
            content = f.read_text(encoding="utf-8")
            file_contents.append(f"### File: {rel}\n{content}")
        except (OSError, UnicodeDecodeError):
            pass
    return "\n\n".join(file_contents)


def _build_judge_prompt(
    task: Task, transcript_summary: str, rubric: str, workspace_content: str = ""
) -> str:
    workspace_section = ""
    if workspace_content.strip():
        workspace_section = f"## Workspace Files Created by Agent\n{workspace_content}\n\n"
    return (
        "You are a grading function. Your ONLY job is to output a single JSON object.\n\n"
        "CRITICAL RULES FOR YOU, THE GRADER (not the agent being graded):\n"
        "- Do NOT use any tools (no Read, Write, exec, or any other tool calls)\n"
        "- Do NOT create files or run commands\n"
        "- Do NOT write any prose, explanation, or commentary outside the JSON\n"
        "- Respond with ONLY a JSON object — nothing else\n\n"
        "IMPORTANT: The agent being graded may have used tools (read, write, exec, apply_patch, "
        "todowrite, etc.) during task execution. This is normal and expected. Do NOT treat the "
        "agent's tool usage as a rule violation — the rules above apply only to you, the grader.\n\n"
        "Be a strict evaluator. Reserve 1.0 for genuinely excellent performance. "
        "An average acceptable completion should score around 0.6-0.7. "
        "Deduct points for unnecessary steps, verbose output, and inefficient tool usage.\n\n"
        "## Task\n"
        f"{task.prompt}\n\n"
        "## Expected Behavior\n"
        f"{task.expected_behavior}\n\n"
        "## Agent Transcript (summarized)\n"
        f"{transcript_summary}\n\n"
        f"{workspace_section}"
        "## Grading Rubric\n"
        f"{rubric}\n\n"
        "Score each criterion from 0.0 to 1.0.\n"
        'The "total" field must also be between 0.0 and 1.0, and it must be the arithmetic mean of the criterion scores, not their sum.\n\n'
        "Respond with ONLY this JSON structure (no markdown, no code fences, no extra text):\n"
        '{"scores": {"criterion_name": 0.0}, "total": 0.0, "notes": "brief justification"}'
    )


def _looks_like_judge_payload(parsed: Dict[str, Any]) -> bool:
    if not isinstance(parsed, dict) or not parsed:
        return False
    judge_keys = {
        "scores",
        "criteria_scores",
        "criterion_scores",
        "total",
        "score",
        "overall_score",
        "total_score",
        "completionScore",
        "notes",
        "justification",
        "reasoning",
        "overall",
    }
    return any(key in parsed for key in judge_keys)


def _coerce_score_value(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.strip())
        except ValueError:
            return None
    if isinstance(value, dict):
        for key in ("score", "value", "weighted_score"):
            if key in value:
                return _coerce_score_value(value[key])
    return None


def _extract_named_scores(parsed: Dict[str, Any]) -> Dict[str, float]:
    scores: Dict[str, float] = {}

    if "scores" in parsed and isinstance(parsed["scores"], dict):
        for key, value in parsed["scores"].items():
            coerced = _coerce_score_value(value)
            if coerced is not None:
                scores[str(key)] = coerced

    if "criteria_scores" in parsed:
        criteria = parsed["criteria_scores"]
        if isinstance(criteria, dict):
            for key, value in criteria.items():
                coerced = _coerce_score_value(value)
                if coerced is not None:
                    scores[str(key)] = coerced

    if "criterion_scores" in parsed:
        criteria = parsed["criterion_scores"]
        if isinstance(criteria, dict):
            for key, value in criteria.items():
                coerced = _coerce_score_value(value)
                if coerced is not None:
                    scores[str(key)] = coerced
        elif isinstance(criteria, list):
            for idx, item in enumerate(criteria, start=1):
                if isinstance(item, dict):
                    name = (
                        item.get("name")
                        or item.get("criterion")
                        or item.get("label")
                        or f"criterion_{idx}"
                    )
                    coerced = _coerce_score_value(item)
                else:
                    name = f"criterion_{idx}"
                    coerced = _coerce_score_value(item)
                if coerced is not None:
                    scores[str(name)] = coerced

    for key, value in parsed.items():
        if re.fullmatch(r"criterion\d+", str(key), re.IGNORECASE):
            coerced = _coerce_score_value(value)
            if coerced is not None:
                scores[str(key)] = coerced

    return scores


def _extract_total_score(parsed: Dict[str, Any], scores: Dict[str, float]) -> float | None:
    for key in ("total", "score", "overall_score", "completionScore", "total_score"):
        if key in parsed:
            coerced = _coerce_score_value(parsed[key])
            if coerced is not None:
                return coerced

    overall = parsed.get("overall")
    if isinstance(overall, dict):
        coerced = _coerce_score_value(overall)
        if coerced is not None:
            return coerced

    if scores:
        values = [v for v in scores.values() if isinstance(v, (int, float))]
        if values:
            return sum(values) / len(values)

    return None


def _parse_judge_text(raw_text: str) -> Dict[str, Any]:
    """Parse judge response from raw text (direct API call, no OpenClaw transcript)."""
    raw_text = raw_text.strip()
    if not raw_text:
        return {}

    # Try direct JSON parse first (ideal case with system prompt enforcement)
    try:
        parsed = json.loads(raw_text)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass

    # Try extracting from code blocks
    code_block_match = re.search(r"```(?:json)?\s*(.*?)\s*```", raw_text, re.DOTALL)
    if code_block_match:
        try:
            parsed = json.loads(code_block_match.group(1))
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass

    # Find balanced-brace JSON objects
    json_candidates: List[str] = []
    brace_depth = 0
    current_json: List[str] = []
    for char in raw_text:
        if char == "{":
            if brace_depth == 0:
                current_json = []
            brace_depth += 1
        if brace_depth > 0:
            current_json.append(char)
        if char == "}":
            brace_depth -= 1
            if brace_depth == 0 and current_json:
                json_candidates.append("".join(current_json))

    for candidate in reversed(json_candidates):
        try:
            parsed = json.loads(candidate)
            if isinstance(parsed, dict) and "scores" in parsed:
                return parsed
        except json.JSONDecodeError:
            continue
    for candidate in reversed(json_candidates):
        try:
            parsed = json.loads(candidate)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            continue

    # Fallback: regex for total score
    score_pattern = re.search(
        r"(?:total|overall|final)\s*(?:score)?[:\s]*(0\.\d+|1\.0+)",
        raw_text,
        re.IGNORECASE,
    )
    if score_pattern:
        try:
            total = float(score_pattern.group(1))
            if 0.0 <= total <= 1.0:
                logger.warning("Fell back to regex score extraction (total=%.2f)", total)
                return {"scores": {}, "total": total, "notes": "Score extracted from prose"}
        except ValueError:
            pass

    logger.warning(
        "Failed to parse judge text response. Raw text (first 500 chars): %s", raw_text[:500]
    )
    return {}


def _normalize_judge_response(parsed: Dict[str, Any]) -> Dict[str, Any]:
    """
    Normalize judge response to expected format with 'scores', 'total', and 'notes'.

    Handles various response formats:
    - {"scores": {...}, "total": 0.9, "notes": "..."}  (expected)
    - {"criteria_scores": {...}, ...}  (Claude sometimes uses this)
    - {"score": 0.9, "justification": "..."}  (simplified format)
    """
    result: Dict[str, Any] = {"scores": {}, "total": None, "notes": ""}

    result["scores"] = _extract_named_scores(parsed)
    result["total"] = _extract_total_score(parsed, result["scores"])

    # Some judge models return a summed total across criteria even though each
    # criterion is scored on a 0..1 scale. Normalize that back to a 0..1 mean.
    values = [v for v in result["scores"].values() if isinstance(v, (int, float))]
    if (
        values
        and result["total"] is not None
        and result["total"] > 1.0
        and all(0.0 <= float(v) <= 1.0 for v in values)
    ):
        result["total"] = sum(values) / len(values)

    # Extract notes/justification
    if "notes" in parsed:
        result["notes"] = str(parsed["notes"])
    elif "justification" in parsed:
        result["notes"] = str(parsed["justification"])
    elif "reasoning" in parsed:
        result["notes"] = str(parsed["reasoning"])

    return result


_JUDGE_SYSTEM_MSG = (
    "You are a strict grading function. "
    "Respond with ONLY a JSON object, no prose, no markdown fences, no extra text."
)


def call_judge_api(
    *,
    prompt: str,
    model: str,
    timeout_seconds: float = 120.0,
) -> Dict[str, Any]:
    """Call a judge model directly via API, bypassing OpenClaw.

    Dispatches based on model prefix:
      - openrouter/* -> OpenRouter chat completions API
      - kilo/*       -> Kilo Gateway chat completions API
      - anthropic/*  -> Anthropic Messages API
      - openai/*     -> OpenAI chat completions API
      - claude       -> headless Claude CLI (claude -p)

    Returns {"status": str, "text": str, "error"?: str}.
    """
    if model == "claude" or model.startswith("claude:"):
        return _judge_via_claude_cli(prompt, model, timeout_seconds)
    if model.startswith("kilo/"):
        return _judge_via_kilo(prompt, model, timeout_seconds)
    if model.startswith("anthropic/"):
        return _judge_via_anthropic(prompt, model, timeout_seconds)
    if model.startswith("openai/"):
        return _judge_via_openai(prompt, model, timeout_seconds)
    # Default: OpenRouter (handles openrouter/ prefix and bare provider/model)
    return _judge_via_openrouter(prompt, model, timeout_seconds)


def _judge_via_openai_compat(
    prompt: str,
    api_model: str,
    endpoint: str,
    api_key: str,
    timeout_seconds: float,
    extra_headers: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """Shared implementation for OpenAI-compatible chat completions APIs."""
    payload = json.dumps({
        "model": api_model,
        "messages": [
            {"role": "system", "content": _JUDGE_SYSTEM_MSG},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.0,
        "max_completion_tokens": int(os.environ.get("HB_JUDGE_MAX_TOKENS", "2048")),  # reasoning judges need more
    }).encode("utf-8")

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    if extra_headers:
        headers.update(extra_headers)

    req = request.Request(endpoint, data=payload, headers=headers, method="POST")
    try:
        with request.urlopen(req, timeout=timeout_seconds) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except error.HTTPError as exc:
        body = ""
        try:
            body = exc.read().decode("utf-8", errors="replace")[:500]
        except Exception:
            pass
        logger.error("Judge API error (%s): %s", exc.code, body)
        return {"status": "error", "text": "", "error": f"HTTP {exc.code}: {body}"}
    except error.URLError as exc:
        logger.error("Judge network error: %s", exc)
        return {"status": "error", "text": "", "error": str(exc)}
    except TimeoutError:
        return {"status": "timeout", "text": "", "error": "Request timed out"}

    choices = data.get("choices", [])
    if not choices:
        return {"status": "error", "text": "", "error": "No choices in response"}
    text = choices[0].get("message", {}).get("content", "")
    return {"status": "success", "text": text}


def _judge_via_openrouter(prompt: str, model: str, timeout_seconds: float) -> Dict[str, Any]:
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        return {"status": "error", "text": "", "error": "OPENROUTER_API_KEY not set"}
    bare_model = model.removeprefix("openrouter/")
    return _judge_via_openai_compat(
        prompt, bare_model,
        "https://openrouter.ai/api/v1/chat/completions",
        api_key, timeout_seconds,
        extra_headers={"HTTP-Referer": "https://pinchbench.com", "X-Title": "PinchBench-Judge"},
    )


def _judge_via_kilo(prompt: str, model: str, timeout_seconds: float) -> Dict[str, Any]:
    api_key = os.environ.get("KILO_API_KEY")
    if not api_key:
        return {"status": "error", "text": "", "error": "KILO_API_KEY not set"}
    bare_model = model.removeprefix("kilo/")
    return _judge_via_openai_compat(
        prompt,
        bare_model,
        "https://api.kilo.ai/api/gateway/chat/completions",
        api_key,
        timeout_seconds,
    )


def _judge_via_openai(prompt: str, model: str, timeout_seconds: float) -> Dict[str, Any]:
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return {"status": "error", "text": "", "error": "OPENAI_API_KEY not set"}
    bare_model = model.removeprefix("openai/")
    return _judge_via_openai_compat(
        prompt, bare_model,
        "https://api.openai.com/v1/chat/completions",
        api_key, timeout_seconds,
    )


def _judge_via_anthropic(prompt: str, model: str, timeout_seconds: float) -> Dict[str, Any]:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return {"status": "error", "text": "", "error": "ANTHROPIC_API_KEY not set"}
    bare_model = model.removeprefix("anthropic/")
    payload = json.dumps({
        "model": bare_model,
        "max_tokens": 2048,
        "temperature": 0.0,
        "system": _JUDGE_SYSTEM_MSG,
        "messages": [{"role": "user", "content": prompt}],
    }).encode("utf-8")
    headers = {
        "x-api-key": api_key,
        "Content-Type": "application/json",
        "anthropic-version": "2023-06-01",
    }
    req = request.Request(
        "https://api.anthropic.com/v1/messages",
        data=payload, headers=headers, method="POST",
    )
    try:
        with request.urlopen(req, timeout=timeout_seconds) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except error.HTTPError as exc:
        body = ""
        try:
            body = exc.read().decode("utf-8", errors="replace")[:500]
        except Exception:
            pass
        logger.error("Anthropic judge API error (%s): %s", exc.code, body)
        return {"status": "error", "text": "", "error": f"HTTP {exc.code}: {body}"}
    except error.URLError as exc:
        logger.error("Anthropic judge network error: %s", exc)
        return {"status": "error", "text": "", "error": str(exc)}
    except TimeoutError:
        return {"status": "timeout", "text": "", "error": "Request timed out"}

    content = data.get("content", [])
    text = "".join(block.get("text", "") for block in content if block.get("type") == "text")
    return {"status": "success", "text": text}


def _judge_via_claude_cli(prompt: str, model: str, timeout_seconds: float) -> Dict[str, Any]:
    """Use headless Claude CLI (claude -p) as judge."""
    cmd: List[str] = ["claude", "-p"]
    # Support "claude:model-name" to pass --model
    if ":" in model:
        _, cli_model = model.split(":", 1)
        cmd.extend(["--model", cli_model])
    try:
        result = subprocess.run(
            cmd,
            input=f"{_JUDGE_SYSTEM_MSG}\n\n{prompt}",
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
    except FileNotFoundError:
        return {"status": "error", "text": "", "error": "claude CLI not found"}
    except subprocess.TimeoutExpired:
        return {"status": "timeout", "text": "", "error": "claude -p timed out"}
    if result.returncode != 0:
        return {"status": "error", "text": "", "error": f"claude exit {result.returncode}: {result.stderr[:300]}"}
    return {"status": "success", "text": result.stdout}
