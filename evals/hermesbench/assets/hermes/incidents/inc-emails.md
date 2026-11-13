# Incident: Duplicate notification emails (2026-02-22)
About 12,000 users received the same order-shipped email two or three times over a 2-hour window. A retry policy in the notifier treated SMTP 4xx "deferred" responses as failures and re-sent immediately. No data loss; some unsubscribe spikes. Fixed by honoring deferred status and adding idempotency keys.
Follow-ups: idempotency keys for all outbound notifications.
Severity: SEV-2
