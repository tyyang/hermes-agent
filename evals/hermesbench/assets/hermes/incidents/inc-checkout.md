# Incident: Checkout errors (2026-02-11)
Between 14:05 and 15:20 UTC about 18% of checkout requests returned HTTP 502. The payments service exhausted its database connection pool after a config deploy reduced `max_pool_size` from 50 to 5. Roughly 2,300 orders failed; revenue impact estimated at $96k. Rolled back the config at 15:12; errors cleared by 15:20.
Follow-ups discussed: add a config validation check for pool size, alert on pool saturation.
Severity: SEV-1
