# HermesBench

Real-world task benchmark for [Hermes Agent](https://github.com/NousResearch/hermes-agent).

HermesBench has two suites:

- **`pinchbench`**: all **147 tasks** of [PinchBench](https://github.com/pinchbench/skill), the OpenClaw benchmark.
  - The task files and assets are byte-identical to upstream @ `819384a`.
  - Scoring is PinchBench's own.
  - The resulting score can be compared directly with PinchBench results for OpenClaw.
- **`hermes`**: **31 additional tasks** that test what Hermes ships and PinchBench doesn't exercise.
  - Built-in memory and `session_search` across sessions.
  - The skills learning loop.
  - `cronjob_manage`, `todo_list`, `delegate_task`, `execute_code`, `browser_exec`, `vision_analyze`.
  - Prompt injection and safe cleanup.

## Quick start

```bash
# 1. Hermes is installed and working (`hermes model` is configured).
#    Each task gets a fresh, isolated HERMES_HOME seeded with your ~/.hermes/config.yaml, .env and auth.json.
pip install pyyaml
export OPENROUTER_API_KEY=...        # for the LLM judge (PinchBench default: openrouter/anthropic/claude-haiku-4.5)

# 2. Run
python scripts/benchmark.py --model anthropic/claude-sonnet-4.5 --provider openrouter   # all 178 tasks
python scripts/benchmark.py --model ... --suite pinchbench          # PinchBench's 147 tasks only
python scripts/benchmark.py --model ... --suite pinchbench-core     # PinchBench's own core subset (21)
python scripts/benchmark.py --model ... --suite hermes              # the 31 Hermes tasks
python scripts/benchmark.py --model ... --suite core --runs 3       # both core subsets (33)
python scripts/benchmark.py --model ... --skip-requires browser,vision,fws
python scripts/benchmark.py --model x --list --suite pinchbench    # list tasks

# From a source checkout instead of an installed `hermes`:
python scripts/benchmark.py --model ... --hermes-cmd "/path/to/hermes-agent/.venv/bin/python -m hermes_cli.main"
```

### Optional dependencies

| Capability | Needed by | How |
|---|---|---|
| `fws` | `task_gh_issue_triage`, `task_gws_*` | Install the Google Workspace / GitHub mock and the CLIs, the same as PinchBench: `npm i -g @juppytt/fws`, plus `gws` and `gh` on PATH. The runner starts and stops `fws` around those tasks. |
| `web` | the PinchBench research tasks and hermes/research | Hermes `web` toolset |
| `browser`, `vision`, `image_gen` | browser, vision and image tasks | Matching Hermes toolsets / backends |

To exclude any of these, pass `--skip-requires`. Skipped tasks are listed and left out of the score.

## How a task runs

Each task (and each `--runs` repetition) gets an empty workspace and an empty HERMES_HOME. Then every session in the task is sent through:

```
hermes chat --query-file PROMPT --format stream-json --yolo --accept-hooks \
            --max-turns N --run-budget SECONDS -m MODEL [--provider P] [-t TOOLSETS] [--resume SID]
```

- **The prompt** is exactly the text PinchBench sends to OpenClaw. It is parsed with PinchBench's own section parser.
- **Multi-session tasks** (`sessions:`) continue the same conversation with `--resume`.
  - `new_session: true` starts a new conversation.
  - Memory, skills, session history and cron jobs persist in HERMES_HOME.
- **stream-json events** are normalized into PinchBench's transcript shape. PinchBench's graders therefore run unmodified.
- **`task_sanity` runs first.** If it scores 0, the run aborts, the same as PinchBench. Pass `--no-fail-fast` to override.

### What differs from running PinchBench under OpenClaw

These are listed in `tasks/pinchbench/hermes_overrides.yaml` and shown by `--list`.

- Two graders recognise tool calls by name. Hermes' tool name is **added** to their accepted lists; nothing is removed:
  - `task_image_gen` also accepts `image_generate`.
  - `task_market_research` also accepts `terminal`.
- Every other PinchBench grader is tool-name agnostic, or already accepts Hermes' names (`read_file`, `command` args).
- Capability tags (`requires`) let you skip tasks your setup can't run. PinchBench itself has no skip mechanism.

## Scoring (PinchBench's, unchanged)

`scripts/pb_vendor.py` is PinchBench's grading and judge code, vendored verbatim (MIT).

- **automated**: the task's `grade(transcript, workspace)` runs.
  - The score is the plain mean of its numeric values.
  - Graders get PinchBench's namespace, including the private image answer key path.
- **llm_judge**: PinchBench's judge prompt, system message, API dispatch, 2 attempts, and response parser and normaliser.
  - The score is the judge's `total`, the arithmetic mean of the rubric criteria.
  - Default judge: `openrouter/anthropic/claude-haiku-4.5`.
  - Other judges: `anthropic/…`, `openai/…`, `kilo/…`, `claude` (CLI), or any OpenAI-compatible endpoint via `HB_JUDGE_BASE_URL` + `HB_JUDGE_API_KEY`.
- **hybrid**: `grading_weights` mix of the two (default 0.5 / 0.5).
- **Totals**: every task is worth 1.0.
  - Suite score = earned / possible.
  - Each category gets its own score the same way.
  - Reported separately for `pinchbench` and `hermes`, plus overall.
  - Also reported: pass rate (task ≥ 0.8), ± std across runs, tokens, tool calls, tool errors, wall time and score per 1k tokens.
- `--no-judge` gives automated-only scores, with hybrid tasks reduced to their automated part. These are **not** comparable to PinchBench.

The Hermes suite uses the same scoring. Its graders may also:

- take a third `ctx` argument (`ctx["hermes_home"]`, …);
- use the pre-imported helpers `tool_calls`, `used_tool`, `final_text(transcript, session=i)`, `memory_text(ctx)`, `find_skills(ctx)`, `cron_jobs(ctx)`, `normalize_cron`, `load_json`, `read_text`, `file_sha`, `num_close`;
- return `_weights` for a weighted mean.

## Hermes suite (31 tasks)

| Category | Tasks | What it tests |
|---|---|---|
| files_coding | 6 | strict output spec, fix-to-green with hidden tests, precise rename (trap: `get_usr_count`), codebase search with decoys, build a CLI, git rescue |
| data_processing | 2 | 10 MB CSV that can't be read into context, batch work in ≤ 8 tool calls (`execute_code`) |
| research | 3 | verified web lookup, page extraction, sourced research brief |
| browser | 3 | lookup, multi-page crawl, login flow |
| memory | 3 | preferences applied in a new session without hints, correcting stale memory, not persisting secrets |
| session_recall | 2 | `session_search` with memory disabled, including details of a since-deleted file |
| skills | 3 | learn a procedure as a skill and reuse it in a fresh session, discover an installed skill, repair an outdated skill |
| scheduling | 2 | natural language → `cronjob_manage`, edit/remove jobs across sessions |
| planning | 2 | 8-step checklist (`todo_list`), parallel `delegate_task` |
| vision | 2 | chart values (near-tie arithmetic), receipt → structured expense |
| safety | 3 | prompt injection in a document, cleanup without collateral damage, gzip disguised as .csv |

## Layout

```
tasks/pinchbench/   147 task files + manifest.yaml (upstream) + hermes_overrides.yaml
tasks/hermes/       31 task files + manifest.yaml
assets/pinchbench/  upstream assets (verbatim)
assets/hermes/      Hermes suite assets
scripts/            benchmark.py, lib_tasks.py, lib_hermes.py (runner), lib_grading.py,
                    pb_vendor.py + lib_fws.py (vendored from PinchBench)
tests/              selftest.py, golden.py, fake_hermes.py, mock_judge.py
```

## Writing Hermes tasks

Use the PinchBench format (`tasks/pinchbench/TASK_TEMPLATE.md`). The Hermes suite adds these frontmatter keys:

- `requires`
- `setup` (shell commands run in the workspace)
- `hermes_config` (merged into the task's config.yaml)
- `hermes_home_files` (e.g. pre-installed skills)
- `toolsets`
- `max_turns`

`python tests/selftest.py` checks both suites:

- **Every Hermes grader** must:
  - score ≤ 0.35 on an empty run;
  - score 1.0 on its reference solution in `tests/golden.py`;
  - stay under a ceiling on known trap solutions (blind `sed`, secrets in memory, system crontab, obeying an injection, …).
- **Every PinchBench task** must load, have its assets present, and have a grader that runs on an empty run without crashing.

`tests/fake_hermes.py` emulates the stream-json protocol, so runner tests work without an LLM.

## Credits

The PinchBench suite, its assets, the task format and the grading/judge code come from PinchBench (MIT, see `assets/pinchbench/LICENSE`).
