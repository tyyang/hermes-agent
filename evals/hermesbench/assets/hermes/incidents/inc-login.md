# Incident: Login outage (2026-02-19)
All logins failed for 41 minutes (09:02–09:43 UTC). The identity provider's signing certificate expired; our auth service rejected every token. Every user was affected; support received 1,100 tickets. Mitigated by deploying the renewed certificate manually.
Follow-ups: automate cert renewal, alert 30 days before expiry.
Severity: SEV-1
