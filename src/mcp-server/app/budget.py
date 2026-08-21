"""Performance-budget loading and evaluation.

Budget format (see .odd/perf-budget.yml): a `budget:` mapping of metric key
to rules. Two rule kinds: `max` (current value must not exceed it) and
`max_increase` (current - baseline must not exceed it).
"""

from __future__ import annotations

import os
from pathlib import Path

import yaml

from .errors import BudgetError


def _odd_dir() -> Path:
    return Path(os.environ.get("ODD_DIR", ".odd"))


def _budget_path() -> Path:
    override = os.environ.get("ODD_BUDGET_FILE")
    return Path(override) if override else _odd_dir() / "perf-budget.yml"


def _value(metric: object) -> float:
    """A metric is either a bare number or a {value, unit} mapping."""
    if isinstance(metric, dict):
        return float(metric["value"])
    return float(metric)  # type: ignore[arg-type]


def load_budget() -> dict | None:
    """Load the budget rules mapping, or None when no budget file exists."""
    path = _budget_path()
    if not path.exists():
        return None
    try:
        parsed = yaml.safe_load(path.read_text())
    except yaml.YAMLError as exc:
        raise BudgetError(f"cannot parse budget file {path}: {exc}") from exc
    rules = (parsed or {}).get("budget")
    if not isinstance(rules, dict):
        raise BudgetError(f"budget file {path} has no 'budget:' mapping")
    return rules


def evaluate_budget(
    budget: dict | None,
    baseline_metrics: dict,
    current_metrics: dict,
) -> tuple[str, list[dict]]:
    """Evaluate budget rules against a baseline/current metrics pair."""
    if budget is None:
        return "no_budget", []
    violations: list[dict] = []
    for metric, rules in budget.items():
        if metric not in current_metrics:
            continue
        current = _value(current_metrics[metric])
        baseline = _value(baseline_metrics[metric]) if metric in baseline_metrics else None
        if "max" in rules and current > rules["max"]:
            violations.append(
                {"metric": metric, "rule": "max", "limit": rules["max"],
                 "baseline": baseline, "current": current}
            )
        if "max_increase" in rules and baseline is not None and current - baseline > rules["max_increase"]:
            violations.append(
                {"metric": metric, "rule": "max_increase", "limit": rules["max_increase"],
                 "baseline": baseline, "current": current}
            )
    return ("fail" if violations else "pass"), violations
