"""Task loading for HermesBench.

Two suites live under tasks/:

  tasks/pinchbench/  all 147 PinchBench tasks, byte-identical to upstream (github.com/pinchbench/skill
                     @ 819384a), plus hermes_overrides.yaml (capability tags, tool-name aliases).
  tasks/hermes/      Hermes-specific tasks (memory, session_search, skills, cron, delegation, ...).

Both use the PinchBench markdown format and are parsed with PinchBench's own section parser, so the
prompt Hermes receives is exactly the prompt OpenClaw receives.

Hermes extensions to the frontmatter (hermes suite only):
  requires, setup, hermes_config, hermes_home_files, toolsets, max_turns — see README.md.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

SUITES = ("pinchbench", "hermes")


@dataclass
class Task:
    task_id: str
    name: str
    suite: str
    category: str
    grading_type: str
    timeout_seconds: int
    prompt: str
    expected_behavior: str
    grading_criteria: List[str]
    automated_checks: Optional[str]
    llm_judge_rubric: Optional[str]
    grading_weights: Optional[Dict[str, float]]
    frontmatter: Dict[str, Any]
    file_path: Path
    assets_dir: Path
    workspace_files: List[Dict[str, Any]] = field(default_factory=list)
    requires: List[str] = field(default_factory=list)
    patches: List[str] = field(default_factory=list)

    @property
    def sessions(self) -> List[Dict[str, Any]]:
        raw = self.frontmatter.get("sessions") or []
        out = []
        for i, s in enumerate(raw):
            if isinstance(s, str):
                out.append({"id": f"s{i + 1}", "prompt": s, "new_session": False})
            elif isinstance(s, dict):
                out.append({"id": s.get("id", f"s{i + 1}"), "prompt": s.get("prompt") or s.get("message", ""),
                            "new_session": bool(s.get("new_session", False))})
        if not out:
            out.append({"id": "main", "prompt": self.prompt, "new_session": True})
        return out

    @property
    def qualified_category(self) -> str:
        return f"{self.suite}/{self.category}"


# ---- PinchBench's parser (lib_tasks.TaskLoader._parse_sections / _extract_grading_criteria), verbatim logic ----

def _parse_sections(body: str) -> Dict[str, str]:
    sections: Dict[str, str] = {}
    current_section = None
    current_content: List[str] = []
    for line in body.split("\n"):
        header_match = re.match(r"^##\s+(.+)$", line)
        if header_match:
            if current_section:
                sections[current_section] = "\n".join(current_content).strip()
            current_section = header_match.group(1)
            current_content = []
        elif current_section:
            current_content.append(line)
    if current_section:
        sections[current_section] = "\n".join(current_content).strip()
    return sections


def _extract_grading_criteria(criteria_text: str) -> List[str]:
    criteria = []
    for line in criteria_text.split("\n"):
        match = re.match(r"^-\s+\[[ x]\]\s+(.+)$", line.strip())
        if match:
            criteria.append(match.group(1))
    return criteria


def load_task(path: Path, suite: str, category: str, assets_dir: Path,
              overrides: Optional[Dict[str, Any]] = None) -> Task:
    content = path.read_text(encoding="utf-8")
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)$", content, re.DOTALL)
    if not m:
        raise ValueError(f"No YAML frontmatter found in {path}")
    fm = yaml.safe_load(m.group(1)) or {}
    sections = _parse_sections(m.group(2))
    task = Task(
        task_id=fm.get("id", ""), name=fm.get("name", ""), suite=suite, category=category,
        grading_type=fm.get("grading_type", "automated"), timeout_seconds=int(fm.get("timeout_seconds", 120)),
        prompt=sections.get("Prompt", "").strip(), expected_behavior=sections.get("Expected Behavior", "").strip(),
        grading_criteria=_extract_grading_criteria(sections.get("Grading Criteria", "")),
        automated_checks=sections.get("Automated Checks", None), llm_judge_rubric=sections.get("LLM Judge Rubric", None),
        grading_weights=fm.get("grading_weights", None), frontmatter=fm, file_path=path, assets_dir=assets_dir,
        workspace_files=list(fm.get("workspace_files") or []), requires=list(fm.get("requires") or []),
    )
    if any("fws" in str(p) for p in fm.get("prerequisites") or []) or fm.get("category") in ("gws", "github"):
        task.requires.append("fws")
    ov = overrides or {}
    task.requires += list((ov.get("requires_by_category") or {}).get(category, []))
    task.requires += list((ov.get("requires") or {}).get(task.task_id, []))
    task.requires = sorted(set(task.requires))
    for old, new in (ov.get("grader_aliases") or {}).get(task.task_id, []):
        if task.automated_checks and old in task.automated_checks:
            task.automated_checks = task.automated_checks.replace(old, new)
            task.patches.append(f"grader alias: {new}")
        else:
            raise ValueError(f"{task.task_id}: override text not found in grader: {old}")
    return task


class TaskLoader:
    def __init__(self, root: Path, assets_root: Path):
        self.root, self.assets_root = root, assets_root
        self.manifests = {s: yaml.safe_load((root / s / "manifest.yaml").read_text(encoding="utf-8")) for s in SUITES}

    def category_order(self) -> List[str]:
        return [f"{s}/{c}" for s in SUITES for c in self.manifests[s]["categories"]]

    def core(self) -> List[str]:
        return [t for s in SUITES for t in (self.manifests[s].get("core") or [])]

    def load_all(self) -> List[Task]:
        tasks: List[Task] = []
        for suite in SUITES:
            man = self.manifests[suite]
            ov_path = self.root / suite / "hermes_overrides.yaml"
            ov = yaml.safe_load(ov_path.read_text(encoding="utf-8")) if ov_path.exists() else {}
            first = list(man.get("run_first") or [])
            suite_tasks = []
            for category, ids in man["categories"].items():
                for tid in ids or []:
                    t = load_task(self.root / suite / f"{tid}.md", suite, category, self.assets_root / suite, ov)
                    if suite == "hermes" and t.frontmatter.get("category") != category:
                        raise ValueError(f"{tid}: frontmatter category != manifest {category!r}")
                    suite_tasks.append(t)
            suite_tasks.sort(key=lambda t: 0 if t.task_id in first else 1)
            tasks += suite_tasks
        ids = [t.task_id for t in tasks]
        dupes = {i for i in ids if ids.count(i) > 1}
        if dupes:
            raise ValueError(f"duplicate task ids across suites: {sorted(dupes)}")
        return tasks
