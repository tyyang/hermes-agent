# Incident: Search relevance degraded (2026-02-14)
For ~6 hours, search results ranked out-of-stock items first. A reindex job ran with a stale synonym file because the artifact cache key ignored the file's hash. No errors were thrown; conversion from search dropped ~4%. Fixed by purging the cache and re-running the index.
Follow-ups: include content hash in cache keys.
Severity: SEV-3
