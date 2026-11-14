#!/usr/bin/env python3
"""Stand-in for `hermes chat ... --format stream-json` used by tests/e2e_fake.sh.

Speaks the same JSONL protocol as hermes_cli/stream_json.py, keeps sessions in $HERMES_HOME so
`--resume` works, and writes memory to $HERMES_HOME/memories like the real memory tool.
"""
import json, os, sys, time, uuid
from pathlib import Path

args = sys.argv[1:]
if args and args[0] == "gateway":  # the runner ensures/stops a per-home gateway around each task
    if args[1:2] == ["ensure"]:  # like real Hermes, lay down a per-home dependency runtime + a task-output spill
        home = Path(os.environ["HERMES_HOME"])
        for rel in ("installs/env/bin/python", "cache/uv/wheel", "cache/terminal-output/out-1.log"):
            (home / rel).parent.mkdir(parents=True, exist_ok=True)
            (home / rel).write_text("x")
    sys.exit(0)
assert args[0] == "chat", args
opt = lambda k: args[args.index(k) + 1] if k in args else None
prompt = Path(opt("--query-file")).read_text()
assert opt("--format") == "stream-json" and "--yolo" in args and opt("--source") is None
home = Path(os.environ["HERMES_HOME"])
assert (home / "config.yaml").exists()
sid = opt("--resume") or uuid.uuid4().hex[:12]
log = home / "fake_calls.jsonl"
with log.open("a") as f:
    f.write(json.dumps({"resume": opt("--resume"), "sid": sid, "cwd": os.getcwd(), "toolsets": opt("-t"),
                        "prompt": prompt[:60]}) + "\n")

def emit(**o):
    print(json.dumps({**o, "timestamp": int(time.time() * 1000)}), flush=True)

emit(type="system", subtype="init", model=opt("-m"), session_id=sid)
answer = "Hello, I'm ready!"
if "remember" in prompt.lower():
    (home / "memories").mkdir(exist_ok=True)
    (home / "memories" / "USER.md").write_text("User prefers metric units; timezone Asia/Taipei (UTC+8).")
    emit(type="tool_use", name="memory", tool_call_id="c1", input={"action": "add", "target": "user"})
    emit(type="tool_result", name="memory", tool_call_id="c1", output='{"success": true}', duration_ms=3, is_error=False)
    answer = "Saved to memory."
elif "Convert both" in prompt:
    mem = (home / "memories" / "USER.md").read_text()
    answer = "23:00–00:30 Taipei time; 22.2 °C." if "Taipei" in mem else "15:00 UTC, 72°F"
elif "app.log" in prompt and "delete" not in prompt:
    emit(type="tool_use", name="read_file", tool_call_id="c2", input={"path": "app.log"})
    emit(type="tool_result", name="read_file", tool_call_id="c2", output=Path("app.log").read_text()[:200], duration_ms=1, is_error=False)
    answer = "KeyError tenant_id"
elif "delete app.log" in prompt:
    Path("app.log").unlink()
    emit(type="tool_use", name="terminal", tool_call_id="c3", input={"command": "rm app.log"})
    emit(type="tool_result", name="terminal", tool_call_id="c3", output="", duration_ms=1, is_error=False)
    answer = "Deleted."
elif "crash log" in prompt:
    emit(type="tool_use", name="session_search", tool_call_id="c4", input={"query": "crash log"})
    emit(type="tool_result", name="session_search", tool_call_id="c4", output="...", duration_ms=1, is_error=False)
    answer = "E-4471, KeyError: 'tenant_id' at billing/invoice.py line 88."
elif "commit message" in prompt.lower():
    Path("COMMIT_MSG.txt").write_text("fix: handle empty cart\n")
    answer = "fix(cart): handle empty cart totals"
for chunk in (answer[: len(answer) // 2], answer[len(answer) // 2:]):
    emit(type="text", text=chunk)
emit(type="result", session_id=sid, exit_code=0, text=answer,
     tokens={"input": 1000, "output": 50, "total": 1050, "cache_read": 0, "cache_write": 0}, duration_ms=10)
print(f"\nsession_id: {sid}", file=sys.stderr)
