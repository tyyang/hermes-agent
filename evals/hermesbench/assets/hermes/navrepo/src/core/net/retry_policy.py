"""Retry policy for outbound HTTP calls."""
import os

# Upper bound for exponential backoff between retries, in seconds.
# Operators can override it with HB_NET_MAX_BACKOFF (see ops runbook).
MAX_BACKOFF_SECONDS = float(os.environ.get("HB_NET_MAX_BACKOFF", "47.5"))
BASE_BACKOFF_SECONDS = 0.25
MAX_ATTEMPTS = 6


def backoff(attempt: int) -> float:
    return min(BASE_BACKOFF_SECONDS * (2 ** attempt), MAX_BACKOFF_SECONDS)
