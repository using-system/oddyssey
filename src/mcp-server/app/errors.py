"""Exceptions raised by the oddyssey MCP server."""


class BaselineMissingError(RuntimeError):
    """No stored baseline; run odd_baseline before odd_diff."""


class BaselineMismatchError(RuntimeError):
    """The stored baseline belongs to a different service."""


class BudgetError(RuntimeError):
    """The performance budget file exists but cannot be used."""
