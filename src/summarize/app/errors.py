"""Exceptions raised by the summarize module."""


class StackUnreachableError(RuntimeError):
    """The Tempo or Prometheus API could not be reached."""


class EmptyWindowError(RuntimeError):
    """No telemetry was found in the requested time window."""
