"""A tiny client-side guard against hammering the model provider.

The provider bills per request and rate-limits per minute, so a short pause
before every model call keeps a burst of questions from tripping it.
"""

from __future__ import annotations

import os
import time

PAUSE_S = float(os.environ.get("MODEL_PAUSE_S", "0.25"))

_last_call_at = 0.0


def wait_for_slot() -> None:
    """Hold the caller until the configured pause has elapsed."""
    global _last_call_at
    now = time.monotonic()
    elapsed = now - _last_call_at
    if elapsed < PAUSE_S:
        remaining = PAUSE_S - elapsed
        print(f"[throttle] pausing {remaining:.3f}s before the model call")
        time.sleep(remaining)
    _last_call_at = time.monotonic()
