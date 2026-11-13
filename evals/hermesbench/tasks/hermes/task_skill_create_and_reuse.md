---
id: task_skill_create_and_reuse
name: Learn a Procedure as a Skill, Then Reuse It
category: skills
grading_type: automated
timeout_seconds: 420
toolsets: skills,file,terminal,code_execution,todo
hermes_config:
  memory:
    memory_enabled: false
    user_profile_enabled: false
workspace_files:
  - path: "data/2026-W05.csv"
    content: |
      team,ticket,hours
      platform,PLAT-101,12.5
      payments,PAY-77,8
      platform,PLAT-108,30.2
      search,SRCH-9,4
      payments,PAY-80,19.7
      search,SRCH-12,6.5
      platform,PLAT-110,1
  - path: "data/2026-W06.csv"
    content: |
      team,ticket,hours
      search,SRCH-14,22
      payments,PAY-91,3.5
      search,SRCH-15,21.3
      platform,PLAT-120,9
      growth,GRW-1,16.4
      payments,PAY-93,40.1
sessions:
  - id: teach
    prompt: |
      Every week I need a report from a timesheet CSV in data/. Rules:
      1. Title line: "# Weekly Hours — <week>", where <week> is the CSV file name without extension (e.g. 2026-W05).
      2. A markdown table with columns Team | Hours, one row per team, total hours rounded to 1 decimal, sorted by hours descending.
      3. Put " ⚠️" after the hours of any team over 40.0 hours.
      4. A final line "Total: <sum> h" (1 decimal).
      5. Save as reports/<week>.md.
      Do it now for data/2026-W05.csv. Then save this procedure as a reusable skill named `weekly-hours-report` so that next time I can just ask for the report without explaining the rules.
  - id: reuse
    new_session: true
    prompt: |
      Make the weekly hours report for data/2026-W06.csv.
---

## Prompt

Multi-session task; see `sessions` in the frontmatter. Session 2 is a new conversation with no rules given — memory is disabled, so the rules must come from the skill.

## Expected Behavior

Session 1: the agent produces `reports/2026-W05.md` (platform 43.7 ⚠️, payments 27.7, search 10.5, total 81.9 h) and creates a skill with `skill_manage` (valid SKILL.md frontmatter with name/description, the five rules, ideally a helper script). Session 2: the agent discovers the skill (`skills_list` / `skill_view`, or it is matched from the skill index in the system prompt), follows it, and writes `reports/2026-W06.md` (payments 43.6 ⚠️, search 43.3 ⚠️, growth 16.4, platform 9.0, total 112.3 h).

## Grading Criteria

- [ ] Skill `weekly-hours-report` exists with valid frontmatter
- [ ] Skill encodes the rules (40 h flag, sorting, rounding, output path)
- [ ] Week 5 report correct
- [ ] Week 6 report exists at the right path
- [ ] Week 6 report correct (order, rounding, flags, total)
- [ ] Session 2 loaded the skill

## Automated Checks

```python
def grade(transcript, workspace_path, ctx):
    import csv
    from collections import defaultdict
    ws = Path(workspace_path)
    skills = find_skills(ctx)
    p = skills.get("weekly-hours-report")
    body = read_text(p) if p else ""
    s = {}
    s["skill_exists"] = 1.0 if p and re.match(r"^---\s*\n.*?^name:.*?^description:.*?^---", body, re.S | re.M) else (0.5 if p else 0.0)
    rules = [r"40", r"desc|descending|sort", r"1 decimal|one decimal|\.1f|round", r"reports/"]
    s["skill_rules"] = sum(bool(re.search(r, body, re.I)) for r in rules) / len(rules)

    def check(week):
        txt = read_text(ws / "reports" / f"{week}.md")
        if not txt:
            return 0.0
        tot = defaultdict(float)
        with open(ws / "data" / f"{week}.csv") as f:
            for r in csv.DictReader(f):
                tot[r["team"]] += float(r["hours"])
        order = sorted(tot, key=lambda t: -tot[t])
        pts = 0.0
        pts += 0.2 if re.search(rf"^#\s*Weekly Hours\s*[—-]\s*{re.escape(week)}\s*$", txt, re.M) else 0.0
        rows = re.findall(r"^\|\s*([A-Za-z]+)\s*\|\s*([\d.]+)\s*(⚠️?)?\s*\|", txt, re.M)
        rows = [r for r in rows if r[0].lower() != "team"]
        pts += 0.3 if [r[0] for r in rows] == order else 0.0
        pts += 0.2 if rows and all(abs(float(h) - round(tot[t], 1)) < 1e-6 and len(h.split(".")[-1]) == 1
                                   for t, h, _ in rows if t in tot) else 0.0
        pts += 0.15 if rows and all(bool(w) == (tot[t] > 40) for t, _, w in rows if t in tot) else 0.0
        pts += 0.15 if re.search(rf"^Total:\s*{sum(tot.values()):.1f}\s*h\s*$", txt, re.M) else 0.0
        return pts
    s["week5_report"] = check("2026-W05")
    s["week6_exists"] = 1.0 if (ws / "reports" / "2026-W06.md").exists() else 0.0
    s["week6_report"] = check("2026-W06")
    s["skill_loaded"] = 1.0 if (used_tool(transcript, "skill_view", session=1)
                                or "weekly-hours-report" in tool_args_text(transcript, session=1)) else 0.0
    return s
```
