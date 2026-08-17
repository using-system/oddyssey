"""Baseline-vs-current diff with budget verdict."""

from __future__ import annotations

from .budget import evaluate_budget


def _delta_entry(before: object, after: object) -> dict:
    if isinstance(before, dict) and isinstance(after, dict):
        entry: dict = {"before": before["value"], "after": after["value"]}
        if "unit" in after:
            entry["unit"] = after["unit"]
        return entry
    return {"before": before, "after": after}


def build_diff(baseline: dict, current: dict, budget: dict | None) -> dict:
    baseline_metrics = baseline.get("metrics", {})
    current_metrics = current.get("metrics", {})
    delta = {
        key: _delta_entry(baseline_metrics.get(key), value)
        for key, value in current_metrics.items()
    }
    verdict, violations = evaluate_budget(budget, baseline_metrics, current_metrics)
    return {
        "odd_version": "1",
        "service": current.get("service"),
        "baseline": baseline,
        "current": current,
        "delta": delta,
        "verdict": verdict,
        "violations": violations,
    }
