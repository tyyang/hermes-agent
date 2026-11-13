---
id: task_todo_multistep
name: Long Checklist Without Dropping Steps
category: planning
grading_type: automated
timeout_seconds: 360
workspace_files:
  - path: "team.csv"
    content: |
      name,role,start_date,email
      Mei Lin,engineer,2026-03-02,mei.lin@example.com
      Omar Haddad,designer,2026-03-09,omar.h@example.com
      Sofia Rossi,engineer,2026-03-16,sofia.rossi@example.com
---

## Prompt

Set up onboarding for the new hires in `team.csv`. All of these, please:

1. Create a folder `onboarding/<first-name-lowercase>/` for each person.
2. In each folder write `welcome.md` that greets them by full name and states their start date.
3. Engineers also get `onboarding/<first>/dev-setup.md` containing the line `Request repo access: #eng-access`.
4. Designers also get `onboarding/<first>/design-setup.md` containing the line `Request Figma seat: #design-ops`.
5. Write `onboarding/schedule.csv` with columns `name,start_date,buddy` sorted by start date, where each person's buddy is the person who started before them (the first person's buddy is `Priya Nair`).
6. Write `onboarding/emails.txt` with all emails, one per line, alphabetically.
7. Write `onboarding/SUMMARY.md` listing how many engineers and designers are starting.
8. Finally, tell me which step was the trickiest and why, in one sentence.

## Expected Behavior

An 8-step request is exactly where Hermes' `todo_list` tool helps the agent track progress. The agent should plan with it, complete every step, and mark items done. The grader checks each artifact; the todo-usage criterion is light (one of seven).

## Grading Criteria

- [ ] Per-person folders and welcome files
- [ ] Engineer dev-setup files (and none for the designer)
- [ ] Designer design-setup file
- [ ] schedule.csv correct
- [ ] emails.txt correct
- [ ] SUMMARY.md counts correct (2 engineers, 1 designer)
- [ ] todo_list used to track the work

## Automated Checks

```python
def grade(transcript, workspace_path):
    ob = Path(workspace_path) / "onboarding"
    people = [("mei", "Mei Lin", "2026-03-02", "engineer"), ("omar", "Omar Haddad", "2026-03-09", "designer"),
              ("sofia", "Sofia Rossi", "2026-03-16", "engineer")]
    s = {}
    s["welcome"] = sum(1 for f, n, d, _ in people if n in read_text(ob / f / "welcome.md")
                       and d in read_text(ob / f / "welcome.md")) / 3
    s["dev_setup"] = (sum("#eng-access" in read_text(ob / f / "dev-setup.md") for f, *_, r in people if r == "engineer") / 2
                      if not (ob / "omar" / "dev-setup.md").exists() else 0.0)
    s["design_setup"] = 1.0 if "#design-ops" in read_text(ob / "omar" / "design-setup.md") else 0.0
    rows = [l.strip() for l in read_text(ob / "schedule.csv").strip().splitlines() if l.strip()]
    expected = ["name,start_date,buddy", "Mei Lin,2026-03-02,Priya Nair", "Omar Haddad,2026-03-09,Mei Lin",
                "Sofia Rossi,2026-03-16,Omar Haddad"]
    s["schedule"] = 1.0 if [r.replace('"', "").replace(", ", ",") for r in rows] == expected else 0.0
    emails = [l.strip() for l in read_text(ob / "emails.txt").splitlines() if l.strip()]
    s["emails"] = 1.0 if emails == sorted(["mei.lin@example.com", "omar.h@example.com", "sofia.rossi@example.com"]) else 0.0
    summ = read_text(ob / "SUMMARY.md").lower()
    s["summary"] = 1.0 if re.search(r"(2|two)\s+engineers?", summ) and re.search(r"(1|one)\s+designers?", summ) else 0.0
    s["todo_used"] = 1.0 if used_tool(transcript, "todo_list") else 0.0
    return s
```
