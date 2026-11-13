---
id: task_skill_discovery
name: Find and Follow an Installed Skill
category: skills
grading_type: automated
timeout_seconds: 300
toolsets: skills,file,terminal,code_execution
workspace_files:
  - path: "invoices/.seq"
    content: "41\n"
hermes_home_files:
  - path: "skills/business/acme-invoice/SKILL.md"
    content: |
      ---
      name: acme-invoice
      description: House rules for creating ACME Consulting invoices for any client. Use whenever the user asks for an invoice.
      version: 1.0.0
      ---

      # ACME invoice conventions

      1. Invoice number: read the integer in `invoices/.seq`, add 1, and format as `ACME-INV-<n zero-padded to 5 digits>`.
         Write the new integer back to `invoices/.seq`.
      2. Save the invoice as `invoices/<invoice number>.md`.
      3. Layout, in this order:
         - `# Invoice <invoice number>`
         - `Bill to: <client>`
         - A markdown table `Item | Qty | Unit (EUR) | Amount (EUR)`
         - `Subtotal: <x> EUR`, `VAT 21%: <x> EUR`, `Total: <x> EUR` (2 decimals, no thousands separators)
         - Final line exactly: `Payment terms: Net 15`
---

## Prompt

Create an invoice for Globex Ltd: 12 hours of consulting at €95/hour plus one travel fee of €40. Follow our company's invoice conventions.

## Expected Behavior

Nothing in the prompt says where the conventions live. Hermes lists installed skills in its system prompt, so the agent should spot `acme-invoice`, load it with `skill_view`, and follow it exactly: invoice ACME-INV-00042, `.seq` → 42, subtotal 1180.00, VAT 247.80, total 1427.80, ending with "Payment terms: Net 15".

## Grading Criteria

- [ ] Skill loaded (skill_view)
- [ ] invoices/ACME-INV-00042.md created
- [ ] .seq updated to 42
- [ ] Amounts correct (1180.00 / 247.80 / 1427.80)
- [ ] Layout follows the skill (heading, Bill to, table, final terms line)

## Automated Checks

```python
def grade(transcript, workspace_path):
    ws = Path(workspace_path)
    inv = read_text(ws / "invoices" / "ACME-INV-00042.md")
    s = {}
    s["skill_loaded"] = 1.0 if used_tool(transcript, "skill_view") or "acme-invoice" in tool_args_text(transcript) else 0.0
    s["file"] = 1.0 if inv else 0.0
    s["seq"] = 1.0 if read_text(ws / "invoices" / ".seq").strip() == "42" else 0.0
    s["amounts"] = sum(bool(re.search(p, inv)) for p in (r"Subtotal:\s*1180\.00 EUR", r"VAT 21%:\s*247\.80 EUR",
                                                          r"Total:\s*1427\.80 EUR")) / 3
    lay = [bool(re.search(r"^#\s*Invoice ACME-INV-00042\s*$", inv, re.M)),
           bool(re.search(r"^Bill to:\s*Globex Ltd", inv, re.M)),
           bool(re.search(r"\|\s*Item\s*\|\s*Qty\s*\|\s*Unit \(EUR\)\s*\|\s*Amount \(EUR\)\s*\|", inv)),
           inv.strip().splitlines()[-1].strip() == "Payment terms: Net 15" if inv.strip() else False]
    s["layout"] = sum(lay) / 4
    return s
```
