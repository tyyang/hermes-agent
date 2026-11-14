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
            --max-turns N -m MODEL [--provider P] [-t TOOLSETS] [--reasoning L] [--resume SID]
```

- **Gateway-mode Hermes** (v0.22+): `hermes chat` runs each session through a gateway owned by the task's HERMES_HOME.
  - The task budget is written to `agent.run_budget_seconds` in the task's config, because gateway chat refuses `--run-budget`.
  - The runner calls `hermes gateway ensure` before the task clock starts, so gateway startup (dependency install, warm-up) is not charged to the agent.
  - It calls `hermes gateway stop` when the task ends.
  - `TELEGRAM_*`, `API_SERVER_*`, `SLACK_*` and `DISCORD_*` lines are dropped from the seeded `.env`. Otherwise each task's gateway would collide with your own running gateway (bot token or port already in use) and exit at startup.

- **The prompt** is exactly the text PinchBench sends to OpenClaw. It is parsed with PinchBench's own section parser.
- **Multi-session tasks** (`sessions:`) continue the same conversation with `--resume`.
  - `new_session: true` starts a new conversation.
  - Memory, skills, session history and cron jobs persist in HERMES_HOME.
- **stream-json events** are normalized into PinchBench's transcript shape. PinchBench's graders therefore run unmodified.
- **`task_sanity` runs first.** If it scores 0, the run aborts, the same as PinchBench. Pass `--no-fail-fast` to override.

- **No secrets left in results.** When a task finishes (including on timeout or error), the runner deletes `.env` and `auth.json` from the task's HERMES_HOME. It also replaces `api_key`/`token`/`secret` values in its `config.yaml` with `REDACTED`. Graders never read those files, so results stay re-gradable. To keep the files for debugging, set `HB_KEEP_SECRETS=1`.
- **Dependency runtime pruned before grading.** Each task's HERMES_HOME installs its own runtime (~1.2 GB). When the task ends (including on timeout or error), before grading, the runner deletes `installs/`, `cache/uv` and `cache/pnpm` from it. The rest of `cache/` (terminal output, scratch files, images) is kept for inspection, and graders that scan the whole home see task state rather than site-packages. If the task's gateway is still running after `gateway stop` (per `gateway.pid`), the runner sends it SIGTERM, then SIGKILL; if it survives, the runtime is kept and a warning is logged. To keep everything, pass `--keep-runtime`.

### Running against a custom OpenAI-compatible endpoint

To benchmark a model served from your own endpoint without touching `~/.hermes`, build a benchmark-only template home. Keep it out of git, because it holds the API key.

1. Create a directory such as `hermes_home_custom/` containing `config.yaml`, `.env` and `auth.json`, usually copied from `~/.hermes`.
2. In its `config.yaml`, set:
   ```yaml
   model:
     provider: custom
     default: org/model
     base_url: https://host/v1
     api_key: ...
   ```
3. Point any `auxiliary.*` tasks that name another provider at `provider: main`.
4. Pass the model as `-m custom:org/model`. Without the `custom:` prefix, Hermes strips `org/` from the name.
5. Omit `--provider`.
6. If the endpoint restricts `reasoning_effort` values, also set `agent.reasoning_effort` and pass `--reasoning`. For example, DeepSeek V4.1 rejects `medium`.
7. If the endpoint uses a private CA, export `SSL_CERT_FILE` pointing at a bundle that includes that CA plus the public roots. Verification stays on.

```bash
python scripts/benchmark.py --model custom:org/model --reasoning high \
    --hermes-home-template "$PWD/hermes_home_custom" --output-dir "$PWD/results.noindex" ...
```

Pass absolute paths to `--hermes-home-template` and `--output-dir`. On macOS, an output directory ending in `.noindex` keeps Spotlight from indexing every task's HERMES_HOME; under load, that indexing can starve gateway startup.

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
  - The `--judge` value is sent as the model name.
  - Set `HB_JUDGE_MAX_TOKENS` (default 2048) higher for reasoning judges. Their reasoning tokens count against the completion budget, and at 2048 the verdict gets cut off.
  - The judge reads its key from the environment only, not from `~/.hermes/.env`.
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

### Known grader false negatives (not fixed)

These were observed with deepseek-v4-flash on Hermes v0.22 (November 2026). The graders are left as-is, so scores stay comparable with PinchBench and earlier HermesBench runs. When reading results, treat these items as possible grader misses rather than model failures.

**1. Tools called from inside `execute_code` are invisible to `used_tool()` (`scripts/lib_grading.py`).**

Hermes' code sandbox can call `web_search`, `web_extract`, `read_file`, `write_file`, `search_files`, `patch` and `terminal` via `from hermes_tools import ...`. The transcript then shows only an `execute_code` call.

| Task | Check | What happened |
|---|---|---|
| hermes/`task_web_rfc_lookup` | `web_used` | Every answer was correct, but the task scored 0.83. It scored 1.00 when the agent called `web_search` directly. |
| hermes/`task_research_brief` | `web_used` | Same check, same exposure. |
| hermes/`task_vision_chart_values` | `vision_used` | Exposed only when `read_file` is called through `execute_code`. |
| pinchbench/`task_market_research` | `used_web_search` | Its own check looks only at tool names and `command` arguments. |

Possible fix: also scan `execute_code` arguments, e.g. `\bweb_search\s*\(` in `arguments.code`.

**2. Regexes that accept only one wording.**

| Task | Check | Agent wrote (correct) | Grader requires |
|---|---|---|---|
| hermes/`task_todo_multistep` | `summary` | `Engineers starting: 2` | `2 engineers` |
| pinchbench/`task_meeting_council_votes` | `summary_count` | `Total motions voted on: 41` | the number before the word `motion` |
| pinchbench/`task_calendar` | `attendee_present` | an `ATTENDEE` line folded per RFC 5545 | the address on a single, unfolded line |

Possible fix for `task_todo_multistep`: accept both word orders, e.g. `(2|two)\s+engineers?|engineers?\b[^\n\d]*?(2|two)\b`. With that, the observed run would score 0.86 instead of 0.71. The PinchBench task files are deliberately left byte-identical to upstream.

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
