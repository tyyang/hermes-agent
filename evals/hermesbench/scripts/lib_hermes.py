"""Run one HermesBench task through the real `hermes` CLI.

Each task gets:
  * an isolated workspace (cwd of the agent) built from workspace_files + setup commands
  * an isolated HERMES_HOME seeded from a template home (config.yaml, .env, auth.json only),
    so memory / skills / sessions / cron jobs start empty and can be inspected by graders.

The agent is driven with the one-shot, machine-readable protocol:

  hermes chat --query-file PROMPT --format stream-json --yolo --accept-hooks \
              --max-turns N --run-budget SECONDS -m MODEL [--provider P] [-t TOOLSETS] [--resume SID]

stream-json events (system/init, text, tool_use, tool_result, result) are normalized into the
PinchBench transcript shape so graders can be shared:

  {"type": "message", "session": i, "message": {"role": "user"|"assistant"|"toolResult", "content": [...]}}
  assistant content items: {"type": "text", "text": ...} | {"type": "toolCall", "name", "arguments", "id"}
"""

from __future__ import annotations

import json
import logging
import os
import re
import shlex
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from lib_fws import fws_available, is_fws_task, start_fws, stop_fws
from lib_tasks import Task

logger = logging.getLogger("hermesbench")

TEMPLATE_FILES = ("config.yaml", ".env", "auth.json")


def deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(base)
    for k, v in (override or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def _place_files(root: Path, specs: List[Dict[str, Any]], assets_dir: Path) -> None:
    for spec in specs or []:
        if "content" in spec:
            dest = root / spec["path"]
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(spec["content"], encoding="utf-8")
        else:
            src = assets_dir / spec["source"]
            dest = root / spec["dest"]
            dest.parent.mkdir(parents=True, exist_ok=True)
            if src.is_dir():
                shutil.copytree(src, dest, dirs_exist_ok=True)
            else:
                shutil.copyfile(src, dest)


def prepare_workspace(task: Task, run_dir: Path, assets_dir: Path) -> Path:
    ws = run_dir / "workspace"
    if ws.exists():
        shutil.rmtree(ws)
    ws.mkdir(parents=True)
    _place_files(ws, task.workspace_files, assets_dir)
    for cmd in task.frontmatter.get("setup") or []:
        env = dict(os.environ, HB_ASSETS=str(assets_dir), GIT_AUTHOR_DATE="2026-01-05T10:00:00",
                   GIT_COMMITTER_DATE="2026-01-05T10:00:00")
        p = subprocess.run(cmd, shell=True, cwd=ws, env=env, capture_output=True, text=True)
        if p.returncode != 0:
            raise RuntimeError(f"{task.task_id}: setup command failed: {cmd}\n{p.stderr}")
    return ws


def prepare_hermes_home(task: Task, run_dir: Path, assets_dir: Path, template: Optional[Path],
                        extra_config: Optional[Dict[str, Any]] = None) -> Path:
    home = run_dir / "hermes_home"
    if home.exists():
        shutil.rmtree(home)
    home.mkdir(parents=True)
    config: Dict[str, Any] = {}
    if template:
        for name in TEMPLATE_FILES:
            src = template / name
            if src.exists():
                shutil.copyfile(src, home / name)
        # `hermes chat` now runs via a per-HERMES_HOME gateway; messaging/api_server creds
        # copied from the real home make that gateway hit fatal startup conflicts (bot token / port in use).
        envf = home / ".env"
        if envf.exists():
            keep = [l for l in envf.read_text(encoding="utf-8").splitlines()
                    if not re.match(r"\s*(export\s+)?(TELEGRAM_|API_SERVER_|SLACK_|DISCORD_)", l)]
            envf.write_text("\n".join(keep) + "\n", encoding="utf-8")
        if (home / "config.yaml").exists():
            config = yaml.safe_load((home / "config.yaml").read_text(encoding="utf-8")) or {}
    # Benchmark baseline: no approval prompts, no cross-task state, memory on (default).
    config = deep_merge(config, extra_config or {})
    config = deep_merge(config, task.frontmatter.get("hermes_config") or {})
    (home / "config.yaml").write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
    _place_files(home, task.frontmatter.get("hermes_home_files") or [], assets_dir)
    return home


class StreamParser:
    """Turn stream-json lines into PinchBench-shaped transcript events."""

    def __init__(self, session_index: int):
        self.session_index = session_index
        self.events: List[Dict[str, Any]] = []
        self._text: List[str] = []
        self.result: Dict[str, Any] = {}
        self.session_id: str = ""
        self.tool_calls = 0
        self.tool_errors = 0

    def _flush_text(self) -> None:
        if self._text:
            text = "".join(self._text)
            self._text = []
            if text.strip():
                self.events.append(self._msg("assistant", [{"type": "text", "text": text}]))

    def _msg(self, role: str, content: List[Dict[str, Any]], **extra: Any) -> Dict[str, Any]:
        return {"type": "message", "session": self.session_index,
                "message": {"role": role, "content": content, **extra}}

    def user(self, prompt: str) -> None:
        self.events.append(self._msg("user", [{"type": "text", "text": prompt}]))

    def feed(self, line: str) -> None:
        line = line.strip()
        if not line:
            return
        try:
            ev = json.loads(line)
        except ValueError:
            return
        t = ev.get("type")
        if t == "system":
            self.session_id = ev.get("session_id") or self.session_id
        elif t == "text":
            self._text.append(ev.get("text", ""))
        elif t == "tool_use":
            self._flush_text()
            self.tool_calls += 1
            self.events.append(self._msg("assistant", [{
                "type": "toolCall", "name": ev.get("name", ""), "arguments": ev.get("input") or {},
                "id": ev.get("tool_call_id", "")}]))
        elif t == "tool_result":
            self._flush_text()
            if ev.get("is_error"):
                self.tool_errors += 1
            self.events.append(self._msg("toolResult", [{"type": "text", "text": ev.get("output", "")}],
                                         toolName=ev.get("name", ""), toolCallId=ev.get("tool_call_id", ""),
                                         isError=bool(ev.get("is_error"))))
        elif t == "result":
            self._flush_text()
            self.result = ev
            self.session_id = ev.get("session_id") or self.session_id
            final = ev.get("text") or ""
            # If text deltas were not streamed (e.g. replay gap), make sure the final answer is present.
            last_texts = [c.get("text", "") for e in self.events if e["message"]["role"] == "assistant"
                          for c in e["message"]["content"] if c.get("type") == "text"]
            if final.strip() and (not last_texts or final.strip() not in last_texts[-1]):
                self.events.append(self._msg("assistant", [{"type": "text", "text": final}]))

    def close(self) -> None:
        self._flush_text()


def build_command(hermes_cmd: str, prompt_file: Path, *, model: str, provider: Optional[str], max_turns: int,
                  run_budget: float, toolsets: Optional[str], resume: Optional[str],
                  reasoning: Optional[str]) -> List[str]:
    cmd = shlex.split(hermes_cmd) + [
        # No `--source tool`: session_search hides source=tool sessions, which would make the
        # session_recall tasks unsolvable. The per-task HERMES_HOME already keeps runs out of the
        # user's own session list.
        "chat", "--query-file", str(prompt_file), "--format", "stream-json", "--yolo", "--accept-hooks",
        "--max-turns", str(max_turns)]  # gateway chat refuses --run-budget
    if model:
        cmd += ["-m", model]
    if provider:
        cmd += ["--provider", provider]
    if toolsets:
        cmd += ["-t", toolsets]
    if reasoning:
        cmd += ["--reasoning", reasoning]
    if resume:
        cmd += ["--resume", resume]
    return cmd


def execute_task(task: Task, *, run_dir: Path, hermes_cmd: str, model: str,
                 provider: Optional[str], template_home: Optional[Path], timeout_multiplier: float = 1.0,
                 reasoning: Optional[str] = None, extra_config: Optional[Dict[str, Any]] = None,
                 extra_env: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    run_dir.mkdir(parents=True, exist_ok=True)
    assets_dir = task.assets_dir
    # PinchBench gws/github tasks talk to the local fws mock (npm i -g @juppytt/fws), exactly as upstream:
    # start it, export its env (HTTPS_PROXY, SSL_CERT_FILE, gws config/token) to the agent, stop after.
    fws_env = None
    if is_fws_task(task.frontmatter):
        if not fws_available():
            logger.warning("%s requires fws but it is not installed (npm install -g @juppytt/fws)", task.task_id)
        else:
            fws_env = start_fws()
    try:
        return _execute(task, run_dir=run_dir, assets_dir=assets_dir, hermes_cmd=hermes_cmd, model=model,
                        provider=provider, template_home=template_home, timeout_multiplier=timeout_multiplier,
                        reasoning=reasoning, extra_config=extra_config, extra_env=extra_env)
    finally:
        if fws_env is not None:
            stop_fws(fws_env)


def _execute(task: Task, *, run_dir: Path, assets_dir: Path, hermes_cmd: str, model: str,
             provider: Optional[str], template_home: Optional[Path], timeout_multiplier: float,
             reasoning: Optional[str], extra_config: Optional[Dict[str, Any]],
             extra_env: Optional[Dict[str, str]]) -> Dict[str, Any]:
    workspace = prepare_workspace(task, run_dir, assets_dir)
    # --run-budget moved to config (agent.run_budget_seconds) in gateway-mode Hermes
    extra_config = deep_merge(extra_config or {}, {"agent": {"run_budget_seconds": int(task.timeout_seconds * timeout_multiplier)}})
    home = prepare_hermes_home(task, run_dir, assets_dir, template_home, extra_config)
    env = dict(os.environ)
    env.update(extra_env or {})
    env["HERMES_HOME"] = str(home)
    env.pop("HERMES_PROFILE", None)

    # start this home's gateway (deps install + warm-up) BEFORE the task clock starts, so
    # gateway startup does not eat the agent's budget (agent.run_budget_seconds only starts once it is ready).
    try:
        subprocess.run(shlex.split(hermes_cmd) + ["gateway", "ensure", "--timeout", "240"], env=env, cwd=workspace,
                       stdin=subprocess.DEVNULL, capture_output=True, timeout=300)
    except Exception as exc:
        logger.warning("%s: gateway ensure failed: %s", task.task_id, exc)
    budget = task.timeout_seconds * timeout_multiplier
    deadline = time.time() + budget
    transcript: List[Dict[str, Any]] = []
    session_results: List[Dict[str, Any]] = []
    usage = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0, "cache_read_tokens": 0}
    tool_calls = tool_errors = 0
    status = "success"
    session_id: Optional[str] = None
    started = time.time()
    raw_log = (run_dir / "stream.jsonl").open("w", encoding="utf-8")

    for i, sess in enumerate(task.sessions):
        remaining = deadline - time.time()
        if remaining <= 5:
            status = "timeout"
            break
        if sess["new_session"]:
            session_id = None
        prompt_file = run_dir / f"prompt_{i}.txt"
        prompt_file.write_text(sess["prompt"], encoding="utf-8")
        cmd = build_command(hermes_cmd, prompt_file, model=model, provider=provider,
                            max_turns=int(task.frontmatter.get("max_turns", 40)), run_budget=remaining,
                            toolsets=task.frontmatter.get("toolsets"), resume=session_id, reasoning=reasoning)
        parser = StreamParser(i)
        parser.user(sess["prompt"])
        raw_log.write(json.dumps({"hb": "session_start", "index": i, "cmd": cmd}) + "\n")
        try:
            proc = subprocess.Popen(cmd, cwd=workspace, env=env, stdin=subprocess.DEVNULL,
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                                    encoding="utf-8", errors="replace")
            try:
                out, err = proc.communicate(timeout=remaining + 30)
            except subprocess.TimeoutExpired:
                proc.kill()
                out, err = proc.communicate()
                status = "timeout"
            for line in out.splitlines():
                raw_log.write(line + "\n")
                parser.feed(line)
            parser.close()
            (run_dir / f"stderr_{i}.log").write_text(err or "", encoding="utf-8")
            rc = proc.returncode
        except FileNotFoundError as exc:
            raise RuntimeError(f"hermes command not found: {hermes_cmd!r} ({exc})") from exc

        transcript.extend(parser.events)
        tok = (parser.result or {}).get("tokens") or {}
        usage["input_tokens"] += int(tok.get("input", 0) or 0)
        usage["output_tokens"] += int(tok.get("output", 0) or 0)
        usage["total_tokens"] += int(tok.get("total", 0) or 0)
        usage["cache_read_tokens"] += int(tok.get("cache_read", 0) or 0)
        tool_calls += parser.tool_calls
        tool_errors += parser.tool_errors
        session_id = parser.session_id or session_id
        session_results.append({"id": sess["id"], "session_id": parser.session_id, "exit_code": rc,
                                "final_text": (parser.result or {}).get("text", ""),
                                "error": (parser.result or {}).get("error")})
        if status == "timeout":
            break
        if rc not in (0, None) and status == "success":
            status = "error"
    raw_log.close()
    try:  # stop this task's gateway so it does not keep running/leaking
        subprocess.run(shlex.split(hermes_cmd) + ["gateway", "stop"], env=env, cwd=workspace,
                       stdin=subprocess.DEVNULL, capture_output=True, timeout=60)
    except Exception:
        pass
    (run_dir / "transcript.json").write_text(json.dumps(transcript, ensure_ascii=False, indent=1), encoding="utf-8")
    return {"task_id": task.task_id, "status": status, "workspace": str(workspace), "hermes_home": str(home),
            "transcript": transcript, "sessions": session_results, "usage": usage, "tool_calls": tool_calls,
            "tool_errors": tool_errors, "execution_time": round(time.time() - started, 2)}
