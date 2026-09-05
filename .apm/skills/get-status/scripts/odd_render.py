"""Render the ODD loop status from the fact sheet, by the skill's rules.

The tables are the rules applied by code - per-service loop state, the
findings ledger and its burn-down, the trends, the open gaps, the next
recommended action - every row citing its inputs. What a rule cannot
decide is not guessed: it lands under "Judgment needed", for the skill
to rule on from the fact sheet and, when it names one, a report body.

Two renderings of the same rules. The default is one screen, the
memory contract's synthesis: one line of inventory, one of memory
invariant (violations only), the burn-down per lineage with the
recommended action and its evidence, what the screen dropped, and the
judgment list ordered by what settling an item changes - a lineage's
boundary first, memory hygiene last - then its items capped. ``full``
renders the working tables whole, the judgment list in the same
order. A caller's rulings on findings (``ruled``) are applied before
either rendering, never after it: one burn-down, one truth.

Standard library only. Imported by odd_status.py for ``--render``.
"""

from __future__ import annotations

import re
import statistics
from datetime import date, datetime, timezone
from itertools import pairwise
from pathlib import Path
from typing import Any

OBSERVATION_MODES = ("drive", "observe", "post-hoc", "re-measure")

FIXED_RE = re.compile(
    r"\b(fixed|closed|resolved|filled|pass(?:ed)?|improved)\b", re.IGNORECASE
)
NOT_FIXED_RE = re.compile(
    r"\b(?:not|never|un)[ -]?(?:fixed|closed|resolved|filled)\b", re.IGNORECASE
)
REGRESSED_RE = re.compile(r"\bregress(?:ed|ion)?\b", re.IGNORECASE)
NEGATED_REGRESSION_RE = re.compile(
    r"\bnot? (?:a )?regress\w*|\bno regression\b|regression check passed|[\"“']regression[\"”']",
    re.IGNORECASE,
)
OPEN_RE = re.compile(
    r"still (present|missing|there)|not ruled|unattributed|\bopen\b|unchanged|carried"
    r"|\bfail(?:ed)?\b",
    re.IGNORECASE,
)
NOT_RULED_RE = re.compile(r"not ruled", re.IGNORECASE)
STRONG_OPEN_RE = re.compile(
    r"still (present|missing|there)|not ruled|unattributed", re.IGNORECASE
)
QUICK_COVERAGE_RE = re.compile(r"\(quick,\s*(\d+) of (\d+) ruled\)", re.IGNORECASE)
COUNTED_VERDICT_RE = re.compile(r"verdict:?\**\s*(\d+)\s*/\s*(\d+)", re.IGNORECASE)
MEASURE_RE = re.compile(
    r"^[~<>≈]?\s*(-?\d+(?:[.,]\d+)?)\s*(ms|s|µs|us|%)?(?:\s*\dxx)?(?:\s*\([^()]*\))?$"
)
UNIT_TO_MS = {"s": 1000.0, "µs": 0.001, "us": 0.001}
OPERATION_HEADER_RE = re.compile(r"operation|route|endpoint|scenario", re.IGNORECASE)
LATENCY_HEADER_RE = re.compile(r"\(ms\)|latency|duration|median|mean", re.IGNORECASE)
GAP_TITLE_RE = re.compile(r"gap", re.IGNORECASE)
PACKAGING_FILE_RE = re.compile(
    r"(^|/)(pyproject\.toml|uv\.lock|poetry\.lock|setup\.cfg|package(-lock)?\.json|"
    r"pnpm-lock\.yaml|yarn\.lock|Cargo\.lock|go\.sum|CHANGELOG\.md|VERSION)$",
    re.IGNORECASE,
)
NO_GAP_RE = re.compile(r"^\**(no handoff|gaps do not dominate|no gap)", re.IGNORECASE)
NOT_QUERIED_RE = re.compile(r"^\**Not queried \(quick\)", re.IGNORECASE)
NOT_QUERIED_NONE_RE = re.compile(
    r"^\**Not queried \(quick\):\**\s*\**none\b", re.IGNORECASE
)
GAP_STATE_RE = re.compile(r"state|status|fate|ruling", re.IGNORECASE)
MIXED_GAPS = "gaps mixed into the not-queried list - see Judgment needed"

TREND_THRESHOLD = (
    0.10  # relative change on the latency metric below which a pair is stable
)
LATENCY_FLOOR = 2.0  # absolute latency change (ms) below which a pair is stable
ERROR_THRESHOLD = 2.0  # percentage points on the error rate
BROKEN_BASELINE_ERROR = 50.0  # a baseline erroring this much measured another path
OVERDUE_FACTOR = 2  # observation overdue past this many median intervals
MAX_GAP_LENGTH = 500
MAX_RULED_BY = 160
MAX_EVIDENCE_COMMITS = 3
MAX_SCREEN_EVIDENCE = 200  # characters of evidence per lineage on the screen
MAX_SCREEN_ITEM = 240  # characters per judgment item on the screen
MAX_SCREEN_ITEMS = 8  # judgment items on the screen, the rest behind --full
ELLIPSIS = "…"
RULED_STATES = {
    "open": "open",
    "fixed": "fixed-and-verified",
    "fixed-and-verified": "fixed-and-verified",
    "regressed": "regressed",
}

STATES = ("open", "fixed-and-verified", "regressed", "declined", "unknown")


# --- small helpers ------------------------------------------------------------


def cap(text: str, limit: int | None) -> tuple[str, bool]:
    if limit is None or len(text) <= limit:
        return text, False
    return text[:limit] + ELLIPSIS, True


def paragraphs(lines: list[str]) -> list[str]:
    out, buf = [], []
    for line in lines + [""]:
        if line.strip():
            buf.append(line.strip())
        elif buf:
            out.append(" ".join(buf))
            buf = []
    return out


def name_of(report: dict) -> str:
    return Path(report["path"]).name


def date_of(report: dict) -> str:
    return name_of(report)[:10]


def mode_of(report: dict) -> str:
    return str(report["frontmatter"].get("mode") or "").lower()


def is_verify(report: dict) -> bool:
    return mode_of(report) == "verify"


def is_quick(report: dict) -> bool:
    return str(report["frontmatter"].get("depth")).lower() == "quick"


def readable(facts: dict) -> list[dict]:
    return [r for r in facts["reports"] if "unreadable" not in r]


# --- classifiers ------------------------------------------------------------


def classify_ruling(text: str | None) -> str:
    """The state a ruling's wording states; ``unknown`` when it states none or two."""
    if not text:
        return "unknown"
    if NOT_FIXED_RE.search(text):
        return "open"
    regressed = REGRESSED_RE.search(NEGATED_REGRESSION_RE.sub("", text)) is not None
    fixed = FIXED_RE.search(text) is not None
    if fixed and (regressed or STRONG_OPEN_RE.search(text)):
        return "unknown"
    if regressed:
        return "regressed"
    if fixed:
        return "fixed-and-verified"
    if OPEN_RE.search(text):
        return "open"
    return "unknown"


def rulings_of(report: dict) -> list[dict]:
    """Every row of a replay report that rules on something, wherever it sits."""
    return [f for f in report.get("findings", []) if f["ruling"]]


def quick_coverage(report: dict) -> tuple[int, int] | None:
    """(ruled, total) for a quick verification, from its own rows."""
    if not is_quick(report):
        return None
    rulings = rulings_of(report)
    if not rulings:
        return None
    not_ruled = sum(NOT_RULED_RE.search(r["ruling"]) is not None for r in rulings)
    return len(rulings) - not_ruled, len(rulings)


def verdict_label(report: dict) -> str:
    """A verification's verdict: its own word first, else its rulings counted."""
    verdict_text = " ".join(report.get("verdict_lines") or [])
    label = None
    for text in (verdict_text, report.get("headline") or ""):
        counted = COUNTED_VERDICT_RE.search(text)
        passes = re.search(r"\bPASS(?:ED)?\b", text) is not None
        fails = re.search(r"\bFAIL(?:ED)?\b", text) is not None
        if passes and fails:
            return "no verdict stated (PASS and FAIL both appear)"
        if passes:
            label = "PASS"
        elif fails:
            label = "FAIL"
        elif counted:
            passed, total = int(counted.group(1)), int(counted.group(2))
            label = f"{'PASS' if passed >= total else 'FAIL'} ({passed}/{total})"
        if label:
            coverage = QUICK_COVERAGE_RE.search(text)
            if coverage:
                label += f" (quick, {coverage.group(1)} of {coverage.group(2)} ruled)"
            break
    if label is None:
        rulings = [
            r for r in rulings_of(report) if not NOT_RULED_RE.search(r["ruling"])
        ]
        if not rulings:
            return "no verdict stated"
        closed = sum(
            classify_ruling(r["ruling"]) == "fixed-and-verified" for r in rulings
        )
        label = f"{closed} of {len(rulings)} rulings closed"
    coverage = quick_coverage(report)
    if coverage and "(quick" not in label:
        label += f" (quick, {coverage[0]} of {coverage[1]} ruled)"
    elif is_quick(report) and "(quick" not in label:
        label += " (quick)"
    return label


# --- lineages ------------------------------------------------------------------


def lineage_label(report: dict) -> str:
    """A lineage: a service set on a stack and an environment, or a plan on
    a stack. The repository a report names is never part of the key - a
    field arriving on a later report must not split a chain - it is stated
    in the row's evidence instead."""
    fm = report["frontmatter"]
    if report["kind"] == "instrumentation":
        return f"{fm.get('project')} (plan) / {fm.get('stack')}"
    services = ", ".join(report["services"]) or "?"
    return f"{services} / {fm.get('stack')} / {fm.get('environment')}"


def repository_note(report: dict, facts: dict) -> str | None:
    """``repository <identity>`` for the evidence of a row whose last report
    names a repository other than the store's, or when the store holds
    reports of several - so a central store's rows say whose code they
    judge; nothing for a single-repository store."""
    where = report.get("repository") or {}
    several = len(facts.get("inventory", {}).get("repositories") or []) > 1
    source = where.get("source")
    if source == "store" and not several:
        return None
    if source == "store":
        if where.get("identity"):
            return f"repository {where['identity']}"
        own = facts.get("repository", {}).get("identity") or "the store"
        return f"repository {own} (the report names none)"
    if source == "unrecognized":
        return f"repository unrecognized ({', '.join(where.get('raw') or [])})"
    return f"repository {', '.join(where.get('identities') or [])}"


def lineages(facts: dict) -> dict[str, list[dict]]:
    """Reports grouped by lineage, chronological, unreadable ones left out."""
    groups: dict[str, list[dict]] = {}
    for report in readable(facts):
        groups.setdefault(lineage_label(report), []).append(report)
    return groups


def verifications_of(facts: dict) -> dict[str, list[dict]]:
    """Verify reports keyed by the name of the report they ``verifies``.

    A re-measure is an observation event, never a verification.
    """
    out: dict[str, list[dict]] = {}
    for report in readable(facts):
        target = report["frontmatter"].get("verifies")
        if is_verify(report) and target:
            out.setdefault(Path(str(target)).name, []).append(report)
    return out


def verification_paths(name: str, by_target: dict[str, list[dict]]) -> list[tuple]:
    """Every verification reaching ``name`` through ``verifies``, oldest first,
    each with the intermediate verifications between ``name`` and it."""
    found: list[tuple] = []
    queue: list[tuple[str, list[dict]]] = [(name, [])]
    seen: set[str] = set()
    while queue:
        current, path = queue.pop(0)
        for verification in by_target.get(current, []):
            if name_of(verification) in seen:
                continue
            seen.add(name_of(verification))
            found.append((verification, path))
            queue.append((name_of(verification), [*path, verification]))
    return sorted(found, key=lambda item: name_of(item[0]))


def verification_chain(name: str, by_target: dict[str, list[dict]]) -> list[dict]:
    """Every verification reaching ``name`` through ``verifies``, oldest first."""
    return [v for v, _ in verification_paths(name, by_target)]


def targets_of(report: dict, by_name: dict[str, dict]) -> list[dict]:
    """The reports a verification reaches downward through ``verifies``."""
    out: list[dict] = []
    current = report
    while True:
        target = current["frontmatter"].get("verifies")
        base = by_name.get(Path(str(target)).name) if target else None
        if base is None or base in out:
            return out
        out.append(base)
        current = base


# --- the findings ledger -----------------------------------------------------------


def own_findings(report: dict) -> list[dict]:
    """A report's own findings: an observation's section 3 rows that rule on nothing."""
    if report["kind"] != "observation":
        return []
    return [f for f in report["findings"] if f["section"] == 3 and not f["ruling"]]


def ruling_on(verification: dict, finding_id: str) -> str | None:
    for row in verification["findings"]:
        if row["id"] == finding_id and row["ruling"]:
            return row["ruling"]
    return None


def finding_rows(facts: dict) -> list[dict]:
    """One row per finding of every observation report, with its state by rule."""
    by_target = verifications_of(facts)
    effective = facts["ledger"]["effective"]
    rows = []
    for report in readable(facts):
        name = name_of(report)
        paths = verification_paths(name, by_target)
        chain_reports = [v for v, _ in paths]
        for finding in own_findings(report):
            key = f"{name} / {finding['id']}"
            state, ruled_by = "open", "no verification yet"
            decision = effective.get(key)
            if decision and str(decision["verdict"]).lower() != "open":
                state = "declined"
                ruled_by = (
                    f"{decision['verdict']} {decision['date']}: {decision['rationale']}"
                )
            else:
                rulings, collision = [], None
                for verification, between in paths:
                    text = ruling_on(verification, finding["id"])
                    if text is None:
                        continue
                    # an intermediate verification defining the same id makes
                    # the later ruling ambiguous: whose finding is it?
                    redefined = [
                        v
                        for v in between
                        if any(f["id"] == finding["id"] for f in own_findings(v))
                    ]
                    if redefined:
                        collision = (verification, text, redefined)
                        continue
                    rulings.append((verification, text))
                if collision:
                    # a later ruling on an id an intermediate report redefined:
                    # whose finding is it? never a state, always a judgment
                    verification, text, redefined = collision
                    state = "unknown"
                    ruled_by = (
                        f"{name_of(verification)}: {text} - but "
                        f"{', '.join(name_of(v) for v in redefined)} also defines "
                        f"{finding['id']}: judge whether it is the same finding"
                    )
                elif rulings:
                    # the newest ruling wins - unless it reads "open" after an
                    # older "fixed" without saying regressed: that is a conflict
                    states = [classify_ruling(text) for _, text in rulings]
                    newest, text = rulings[-1]
                    if states[-1] == "open" and "fixed-and-verified" in states[:-1]:
                        state = "unknown"
                        ruled_by = "verifications disagree: " + "; ".join(
                            f"{name_of(v)}: {t}" for v, t in rulings
                        )
                    else:
                        state = states[-1]
                        ruled_by = f"{name_of(newest)}: {text}"
                elif chain_reports:
                    ruled_by = (
                        f"not ruled by {', '.join(name_of(v) for v in chain_reports)}"
                    )
            rows.append(
                {
                    "report": report["path"],
                    "id": finding["id"],
                    "title": finding["title"],
                    "severity": finding["severity"],
                    "state": state,
                    "ruled_by": ruled_by,
                }
            )
    return rows


def out_of_chain_rulings(facts: dict, ruled: frozenset[str] = frozenset()) -> list[str]:
    """Rulings a verification carries on an id no report in its chain defines,
    while another report does - the same finding, or a homonym: a judgment.

    An item is settled, and dropped, once the caller ruled every finding
    it names (``ruled`` holds their ledger keys)."""
    by_name = {name_of(r): r for r in readable(facts)}
    definers: dict[tuple[str, str], list[str]] = {}
    for report in readable(facts):
        for finding in own_findings(report):
            key = (lineage_label(report), finding["id"])
            definers.setdefault(key, []).append(name_of(report))
    out = []
    for verification in readable(facts):
        if not is_verify(verification):
            continue
        targets = targets_of(verification, by_name)
        if any(t["kind"] == "instrumentation" for t in targets):
            continue  # its rulings are on plan items, not on findings
        in_chain = {name_of(t) for t in targets}
        for row in rulings_of(verification):
            defined = definers.get((lineage_label(verification), row["id"]), [])
            if defined and not any(d in in_chain for d in defined):
                if all(f"{d} / {row['id']}" in ruled for d in defined):
                    continue
                out.append(
                    f"{name_of(verification)} rules {row['id']} "
                    f"({cap(row['ruling'], MAX_RULED_BY)[0]}), an id of "
                    f"{', '.join(defined)} outside its chain: judge whether it is the same "
                    "finding"
                )
    return out


def burn_down(rows: list[dict]) -> dict[str, int]:
    return {state: sum(r["state"] == state for r in rows) for state in STATES}


def parse_ruling(text: str) -> tuple[str, str] | str:
    """``<report>/<id>=<state>`` as (key, state); a problem string otherwise."""
    if "=" not in text:
        return f"ruling {text}: not <report>/<id>=<state>"
    ref, _, state = text.rpartition("=")
    if "/" not in ref:
        return f"ruling {text}: not <report>/<id>=<state>"
    report, _, finding_id = ref.rpartition("/")
    key = f"{Path(report.strip()).name} / {finding_id.strip()}"
    normalized = RULED_STATES.get(state.strip().lower())
    if normalized is None:
        return f"ruling {key}: unknown state '{state.strip()}'"
    return key, normalized


# The problems apply_rulings returns for a ruling it refused - a key no
# report carries, a finding the ledger declined - as opposed to a flag it
# could not parse. Anchored at the end: a caller's text embedding the words
# renders as a parse problem, whose suffix is the form the flag missed.
RULING_REFUSED_RE = re.compile(r": (no such finding|declined by the ledger \(.*\))$")


def apply_rulings(
    rows: list[dict], ruled: list[str] | tuple[str, ...]
) -> tuple[list[str], frozenset[str]]:
    """The caller's rulings applied to the finding rows.

    Returns the problems (deferred) and the keys of the findings ruled.
    A ruling names a finding by its ledger key; it never overrides the
    ledger itself - a declined finding stays declined and the ruling is
    deferred - and a key no report carries is deferred too.
    """
    problems: list[str] = []
    applied: set[str] = set()
    by_key = {f"{Path(r['report']).name} / {r['id']}": r for r in rows}
    for text in ruled:
        parsed = parse_ruling(text)
        if isinstance(parsed, str):
            problems.append(parsed)
            continue
        key, state = parsed
        row = by_key.get(key)
        if row is None:
            problems.append(f"ruling {key}: no such finding")
        elif row["state"] == "declined":
            verdict = row["ruled_by"].split(": ", 1)[0]
            problems.append(f"ruling {key}: declined by the ledger ({verdict})")
        else:
            row["state"] = state
            row["ruled_by"] = f"ruled by the caller ({row['ruled_by']})"
            applied.add(key)
    return problems, frozenset(applied)


def plural(count: int, noun: str) -> str:
    return f"{count} {noun}" + ("" if count == 1 else "s")


def last_report_label(report: dict) -> str:
    slug = Path(report["path"]).stem[len("YYYY-MM-DD-HHmm-") :]
    kind = "plan" if report["kind"] == "instrumentation" else mode_of(report)
    return f"{date_of(report)} {slug} ({kind})"


def loop_state_rows(
    facts: dict, rows: list[dict], recs: list[dict], evidence_cap: int | None
) -> tuple[list[list[str]], list[str]]:
    """One row per lineage - the last report, the burn-down, the action - and
    one evidence line per lineage, kept out of the table so it stays narrow."""
    by_name = {name_of(r): r for r in readable(facts)}
    counts: dict[str, dict[str, int]] = {}
    for r in rows:
        label = lineage_label(by_name[Path(r["report"]).name])
        counts.setdefault(label, {s: 0 for s in STATES})[r["state"]] += 1
    actions = {r["lineage"]: r for r in recs}
    table, evidence = [], []
    for label, line in lineages(facts).items():
        c = counts.get(label, {s: 0 for s in STATES})
        rec = actions.get(label, {"action": "?", "evidence": ""})
        table.append(
            [
                label,
                last_report_label(line[-1]),
                *(str(c[s]) for s in STATES),
                rec["action"],
            ]
        )
        evidence.append(f"- {label}: {cap(rec['evidence'], evidence_cap)[0]}")
    return table, evidence


def screen_lines(facts: dict) -> list[str]:
    """The inventory and the memory invariant, one line each."""
    inventory = facts["inventory"]
    reports = readable(facts)
    kinds = {
        k: sum(r["kind"] == k for r in reports)
        for k in ("observation", "instrumentation")
    }
    ledger = facts["ledger"]
    skipped = [r for r in ledger["rows"] if r["status"] == "skipped"]
    ledger_text = (
        f"ledger: {sum(r['status'] == 'ok' for r in ledger['rows'])} row(s)"
        + (f", {len(skipped)} skipped" if skipped else "")
        if ledger["present"]
        else "ledger: absent"
    )
    classifications = facts.get("classifications") or {"present": False, "rows": []}
    skipped_classes = [r for r in classifications["rows"] if r["status"] == "skipped"]
    classifications_text = (
        f"classifications: "
        f"{sum(r['status'] == 'ok' for r in classifications['rows'])} row(s)"
        + (f", {len(skipped_classes)} skipped" if skipped_classes else "")
        if classifications["present"]
        else "classifications: absent"
    )
    head = facts["head"] or {}
    repositories = repositories_of(facts)
    invariant = facts.get("invariant") or {
        "checked": 0,
        "violations": [],
        "legacy": [],
    }
    violations = invariant["violations"]
    legacy = invariant.get("legacy", [])
    if not violations and not skipped and not skipped_classes:
        status = (
            f"clean ({invariant['checked']} of {invariant['checked']}"
            + (f"; {len(legacy)} predate `depth`, read as full" if legacy else "")
            + ")"
        )
    else:
        problems = (
            [f"{Path(v['path']).name} - {p}" for v in violations for p in v["problems"]]
            + [f"decisions.md line {r['line']} - {r['reason']}" for r in skipped]
            + [
                f"entry-classifications.md line {r['line']} - {r['reason']}"
                for r in skipped_classes
            ]
        )
        status = (
            f"{plural(len(violations), 'violation')}, "
            f"{plural(len(skipped) + len(skipped_classes), 'ledger row')} skipped"
            + (f", {len(legacy)} predate `depth`" if legacy else "")
            + ": "
            + "; ".join(problems)
        )
    return [
        (
            f"- {facts['matched']} matched of {inventory['report_count']} stored "
            f"({kinds['observation']} observation, {kinds['instrumentation']} "
            f"instrumentation) · services: {', '.join(inventory['services']) or 'none'} "
            f"· stacks: {', '.join(inventory['stacks']) or 'none'} · environments: "
            f"{', '.join(inventory['environments']) or 'none'}"
            + (f" · repositories: {', '.join(repositories)}" if repositories else "")
            + f" · {ledger_text} · {classifications_text} · HEAD "
            f"{str(head.get('sha', '?'))[:7]} ({str(head.get('date', '?'))[:10]})"
        ),
        f"- memory invariant: {status}",
        "",
    ]


# --- trends ------------------------------------------------------------------------


def measurement(text: str | None) -> float | None:
    """A bare measurement (``80 ms``, ``4.75``, ``10 % (1×502)``), else None."""
    if not text:
        return None
    match = MEASURE_RE.match(re.sub(r"\*+", "", text).strip())
    if not match:
        return None
    return float(match.group(1).replace(",", ".")) * UNIT_TO_MS.get(match.group(2), 1.0)


def per_operation_table(report: dict) -> dict | None:
    for section in report.get("sections", []):
        if section["number"] != 2:
            continue
        for table in section["tables"]:
            if table["header"] and OPERATION_HEADER_RE.search(table["header"][0]):
                return table
    return None


def column_index(header: list[str], pattern: str) -> int | None:
    for index, header_cell in enumerate(header):
        if re.search(pattern, header_cell, re.IGNORECASE):
            return index
    return None


def cell(row: list[str], index: int | None) -> str | None:
    if index is None or index >= len(row):
        return None
    return row[index].strip() or None


def arrow(before: str | None, after: str | None) -> str:
    if before is None and after is None:
        return "-"
    return f"{before or '-'} -> {after or '-'}"


def trend_of(before: dict, after: dict, metric: str) -> str:
    """The trend by rule: the error rate first, then the latency metric named."""
    err_a, err_b = measurement(before["error"]), measurement(after["error"])
    if err_a is None or err_b is None:
        return "n/a (error rate not parsable)"
    if err_a >= BROKEN_BASELINE_ERROR:
        return "n/a (baseline error rate >= 50 %, not comparable)"
    if err_b - err_a > ERROR_THRESHOLD:
        return f"regressed (error {before['error']} -> {after['error']})"
    lat_a, lat_b = measurement(before[metric]), measurement(after[metric])
    if lat_a is None or lat_b is None or lat_a == 0:
        return "n/a (latency not parsable)"
    change = (lat_b - lat_a) / lat_a
    label = before.get("label", metric)
    if abs(lat_b - lat_a) < LATENCY_FLOOR:
        return "stable"
    if change <= -TREND_THRESHOLD:
        return f"improved ({label} {change:+.0%})".replace("%", " %")
    if change >= TREND_THRESHOLD:
        return f"regressed ({label} {change:+.0%})".replace("%", " %")
    return "stable"


def operation_values(table: dict) -> dict[str, dict]:
    """Per operation: p50, p95, p99, error - or one latency column as a fallback."""
    header = table["header"]
    columns = {
        "p50": column_index(header, r"^p50|median"),
        "p95": column_index(header, r"^p95"),
        "p99": column_index(header, r"^p99"),
        "error": column_index(header, r"error"),
    }
    label = None
    if columns["p50"] is None and columns["p95"] is None:
        latency = column_index(header, r"server.*\(ms\)")
        if latency is None:
            latency = next(
                (
                    i
                    for i, h in enumerate(header)
                    if i > 0 and LATENCY_HEADER_RE.search(h)
                ),
                None,
            )
        if latency is not None:
            columns["p50"], label = latency, header[latency].strip()
    values = {}
    for row in table["rows"]:
        if row and row[0].strip():
            entry = {k: cell(row, i) for k, i in columns.items()}
            if label:
                entry["label"] = label
            values[row[0].strip()] = entry
    return values


def trend_rows(facts: dict) -> tuple[list[dict], list[dict]]:
    """Trends over every verifies pair, and the runs listed apart with why."""
    by_name = {name_of(r): r for r in readable(facts)}
    rows: list[dict] = []
    apart: list[dict] = []
    paired: set[tuple[str, str]] = set()
    for report in readable(facts):
        target = report["frontmatter"].get("verifies")
        if mode_of(report) not in ("verify", "re-measure") or not target:
            continue
        base = by_name.get(Path(str(target)).name)
        if base is None or base["kind"] == "instrumentation":
            continue
        paired.add((name_of(base), name_of(report)))
        before, after = per_operation_table(base), per_operation_table(report)
        if before is None or after is None:
            apart.append(
                {
                    "reports": [name_of(base), name_of(report)],
                    "reason": "per-operation table not lifted on one side",
                }
            )
            continue
        values_a, values_b = operation_values(before), operation_values(after)
        for operation in values_a:
            if operation not in values_b:
                continue
            a, b = values_a[operation], values_b[operation]
            metric = "p95" if a.get("p95") and b.get("p95") else "p50"
            p50 = arrow(a["p50"], b["p50"])
            if a.get("label"):
                p50 = f"{a['label']}: {p50}"
            rows.append(
                {
                    "pair": f"{name_of(base)} -> {name_of(report)}",
                    "operation": operation,
                    "p50": p50,
                    "p95": arrow(a["p95"], b["p95"]),
                    "p99": arrow(a["p99"], b["p99"]),
                    "error": arrow(a["error"], b["error"]),
                    "trend": trend_of(a, b, metric),
                }
            )
    for line in lineages(facts).values():
        observations = [r for r in line if r["kind"] == "observation"]
        for earlier, later in pairwise(observations):
            if (name_of(earlier), name_of(later)) in paired:
                continue
            apart.append(
                {
                    "reports": [name_of(earlier), name_of(later)],
                    "reason": "not a verifies pair: comparability of the scenarios is a judgment",
                }
            )
    return rows, apart


# --- boundaries and recommendations -------------------------------------------------


def with_paths(entries: list[str], paths: dict) -> str:
    parts = []
    for entry in entries:
        found = paths.get(entry)
        parts.append(f"{entry} ({', '.join(found['paths'][:3])})" if found else entry)
    return "; ".join(parts)


def boundary(report: dict) -> dict:
    """What moved since the report, by its preferred boundary.

    ``changed`` is True, False, or None when the rules cannot tell.
    """
    where = report.get("repository") or {}
    if where.get("source") == "unreachable":
        identity = where["identity"]
        hint = (
            " (the store's own identity is unknown: no origin remote to compare with)"
            if where.get("store_identity_unknown")
            else ""
        )
        return {
            "changed": None,
            "evidence": (
                f"boundary unknown: {identity} is not reachable from here - "
                f"pass --repository {identity}=<path to its clone>{hint}"
            ),
        }
    if where.get("source") == "unrecognized":
        return {
            "changed": None,
            "evidence": (
                "boundary unknown: the report's repository value is not a remote "
                f"the rules can read ({', '.join(where.get('raw') or [])}) - never "
                "read as the store's own"
            ),
        }
    if where.get("source") == "spans":
        return {
            "changed": None,
            "evidence": (
                "boundary unknown: the report spans repositories "
                f"{', '.join(where['identities'])} - one revision and one anchor "
                "cannot cover both"
            ),
        }
    diff = report.get("tree_anchor_diff")
    since = report["commits_since"]
    if diff is not None:
        paths = diff.get("changed_paths") or {}
        if diff.get("runtime"):
            packaging_only = all(
                paths.get(entry)
                and paths[entry]["count"] == len(paths[entry]["paths"])
                and all(PACKAGING_FILE_RE.search(p) for p in paths[entry]["paths"])
                for entry in diff["runtime"]
            )
            if packaging_only:
                return {
                    "changed": None,
                    "evidence": (
                        "boundary uncertain: runtime entries differ only in packaging "
                        f"files ({with_paths(diff['runtime'], paths)}) - a version bump or "
                        "a dependency change, judge from the diff"
                    ),
                }
            return {
                "changed": True,
                "evidence": (
                    "runtime entries differ since the tree anchor: "
                    f"{with_paths(diff['runtime'], paths)}"
                ),
            }
        uncertain = []
        if diff["unclassified"]:
            count = len(diff["unclassified"])
            uncertain.append(
                f"{count} {'entry' if count == 1 else 'entries'} the anchor cannot classify "
                f"({with_paths(diff['unclassified'], paths)})"
            )
        if diff["only_at_candidate"]:
            uncertain.append(f"only at HEAD: {', '.join(diff['only_at_candidate'])}")
        if diff["only_in_anchor"]:
            uncertain.append(f"gone from HEAD: {', '.join(diff['only_in_anchor'])}")
        if uncertain:
            return {
                "changed": None,
                "evidence": "boundary uncertain: " + "; ".join(uncertain),
            }
        if diff["non_runtime"]:
            return {
                "changed": False,
                "evidence": (
                    "only non-runtime entries moved since the tree anchor: "
                    f"{', '.join(diff['non_runtime'])}"
                ),
            }
        return {"changed": False, "evidence": "tree anchor equals HEAD"}
    count = since["count"]
    if since["boundary"] == "revision":
        if count:
            listed = since["commits"] or []
            subjects = "; ".join(c["subject"] for c in listed[:MAX_EVIDENCE_COMMITS])
            shown = (
                f"first {MAX_EVIDENCE_COMMITS}: "
                if count > MAX_EVIDENCE_COMMITS
                else ""
            )
            return {
                "changed": True,
                "evidence": (
                    f"{count} commit(s) since the revision, {since['scope']}: "
                    f"{shown}{subjects}"
                ),
            }
        return {"changed": False, "evidence": "no commit since the revision"}
    if since["boundary"] == "commit-date":
        if count:
            return {
                "changed": None,
                "evidence": (
                    "commit-date boundary (no anchor, revision unresolved): "
                    f"{count} commit(s) since, {since['scope']} - coverage uncertain"
                ),
            }
        return {
            "changed": False,
            "evidence": "no commit since the report's commit date",
        }
    return {"changed": None, "evidence": "no boundary: the report is not committed"}


def unruled_by_quick(report: dict, by_name: dict[str, dict]) -> tuple[str, int] | None:
    """(baseline, count) of a baseline's findings a quick verification left unruled."""
    if not (is_verify(report) and is_quick(report)):
        return None
    targets = targets_of(report, by_name)
    if not targets:
        return None
    base = targets[0]
    ruled = {row["id"] for row in rulings_of(report)}
    unruled = [f for f in own_findings(base) if f["id"] not in ruled]
    return (name_of(base), len(unruled)) if unruled else None


def parse_day(text: str | None) -> date | None:
    try:
        return date.fromisoformat(str(text)[:10])
    except ValueError:
        return None


def cadence(observations: list[dict], today: date) -> dict | None:
    days = sorted({parse_day(date_of(r)) for r in observations} - {None})
    if len(days) < 3:
        return None
    gaps = [(b - a).days for a, b in pairwise(days)]
    median = max(statistics.median(gaps), 1)
    elapsed = (today - days[-1]).days
    return {
        "median": median,
        "elapsed": elapsed,
        "overdue": elapsed > OVERDUE_FACTOR * median,
    }


def chain(line: list[dict]) -> str:
    observations = [r for r in line if r["kind"] == "observation" and not is_verify(r)]
    verifications = [r for r in line if is_verify(r)]
    if verifications and any(
        not v["frontmatter"].get("verifies") for v in verifications
    ):
        return "unknown (pre-convention)"
    if not observations:
        return "verifications only"
    last_obs = max(observations, key=name_of)
    parts = [
        f"observed {date_of(last_obs)} ({last_obs['frontmatter'].get('run_name')})"
    ]
    moved = boundary(last_obs)
    if moved["changed"]:
        parts.append("fixed")
    elif moved["changed"] is None:
        parts.append("change since: uncertain")
    later = [v for v in verifications if name_of(v) > name_of(last_obs)]
    if later:
        parts.append(f"verified {date_of(later[-1])} ({verdict_label(later[-1])})")
    return " -> ".join(parts)


def recommendations(facts: dict, today: str | date | None = None) -> list[dict]:
    """One action per lineage, by the maturity rules, with its inputs."""
    day = (
        today
        if isinstance(today, date)
        else (parse_day(today) or datetime.now(timezone.utc).date())
    )
    by_target = verifications_of(facts)
    by_name = {name_of(r): r for r in readable(facts)}
    out = []
    for label, line in lineages(facts).items():
        last = line[-1]
        note = repository_note(last, facts)
        if last["kind"] == "instrumentation":
            covering = verification_chain(name_of(last), by_target)
            if covering:
                v = covering[-1]
                action = "plan verified"
                evidence = (
                    f"{name_of(v)}: {verdict_label(v)}; since the plan: "
                    f"{boundary(last)['evidence']} (the service's observation lineage carries it)"
                )
            else:
                action = "plan awaits verification"
                evidence = (
                    f"no report verifies {name_of(last)}; {boundary(last)['evidence']}"
                )
            if note:
                evidence = f"{note}; {evidence}"
            out.append({"lineage": label, "action": action, "evidence": evidence})
            continue
        bound = boundary(last)
        observations = [r for r in line if mode_of(r) in OBSERVATION_MODES]
        rhythm = cadence(observations, day)
        evidence = [f"last report {name_of(last)} ({mode_of(last)})"]
        if note:
            evidence.append(note)
        if is_verify(last):
            evidence.append(f"verdict {verdict_label(last)}")
        evidence.append(bound["evidence"])
        unruled = unruled_by_quick(last, by_name)
        if unruled:
            action = "judgment needed"
            evidence.append(
                f"{unruled[1]} finding(s) of {unruled[0]} unruled by the quick verification: "
                "verified only for the items it ruled, never for the service"
            )
        elif bound["changed"] is None:
            action = "judgment needed"
        elif bound["changed"]:
            action = "verification due"
        elif rhythm and rhythm["overdue"]:
            action = "observation overdue"
            evidence.append(
                f"observed every {rhythm['median']:g} days, last {rhythm['elapsed']} days ago"
            )
        elif is_verify(last):
            action = "loop can rest"
        else:
            action = "fix pending"
            evidence.append("no verification yet, no change since the report")
        out.append(
            {"lineage": label, "action": action, "evidence": "; ".join(evidence)}
        )
    return out


# --- gaps ----------------------------------------------------------------------------


def gap_section(report: dict) -> dict | None:
    return next(
        (
            s
            for s in report.get("sections", [])
            if s["number"] == 5 and GAP_TITLE_RE.search(s["title"])
        ),
        None,
    )


def gap_items(section: dict) -> list[str]:
    """The gaps a section records: its bullets, its table rows, else its paragraphs."""
    bullets = [
        t[2:].strip() for t in section["text"].splitlines() if t.startswith("- ")
    ]
    from_tables = []
    for table in section["tables"]:
        state = column_index(table["header"], GAP_STATE_RE.pattern)
        for row in table["rows"]:
            if row and row[0].strip():
                text = row[0].strip()
                if state is not None and state < len(row) and row[state].strip():
                    text += f" ({row[state].strip()})"
                from_tables.append(text)
    return bullets + from_tables or paragraphs(section["text"].splitlines())[:3]


def is_not_queried_item(item: str) -> bool:
    """A not-queried item hides its gaps - unless the list it opens with is ``none``."""
    return (
        NOT_QUERIED_RE.match(item) is not None
        and NOT_QUERIED_NONE_RE.match(item) is None
    )


def newest_observations(facts: dict) -> dict[str, dict]:
    out = {}
    for label, line in lineages(facts).items():
        observations = [r for r in line if r["kind"] == "observation"]
        if observations:
            out[label] = observations[-1]
    return out


def mixed_not_queried(facts: dict) -> list[str]:
    """Quick reports whose gaps section opens an item with its not-queried list:
    the item is not a gap, and the gaps it carries cannot be told apart."""
    out = []
    for newest in newest_observations(facts).values():
        section = gap_section(newest)
        if section is None or section["text"] is None or not is_quick(newest):
            continue
        if any(is_not_queried_item(item) for item in gap_items(section)):
            out.append(name_of(newest))
    return out


def gap_rows(facts: dict) -> list[dict]:
    """The newest observation of each lineage, its telemetry-gaps section as recorded.

    A quick report's ``Not queried (quick)`` item is a statement about
    that mission, never a gap: the item is dropped whole and deferred.
    """
    rows = []
    for label, newest in newest_observations(facts).items():
        section = gap_section(newest)
        if section is None or section["text"] is None:
            rows.append(
                {
                    "lineage": label,
                    "gap": "(section 5 not lifted)",
                    "recorded_by": name_of(newest),
                    "truncated": False,
                }
            )
            continue
        quick = is_quick(newest)
        before = len(rows)
        dropped = False
        for item in gap_items(section):
            if not item or NO_GAP_RE.match(item):
                continue
            if quick and is_not_queried_item(item):
                dropped = True
                continue
            gap, truncated = cap(item, MAX_GAP_LENGTH)
            if quick:
                gap = f"(quick report) {gap}"
            rows.append(
                {
                    "lineage": label,
                    "gap": gap,
                    "recorded_by": name_of(newest),
                    "truncated": truncated or bool(section["text_truncated"]),
                }
            )
        if dropped and len(rows) == before:
            rows.append(
                {
                    "lineage": label,
                    "gap": f"(quick report) {MIXED_GAPS}",
                    "recorded_by": name_of(newest),
                    "truncated": False,
                }
            )
    return rows


# --- rendering -----------------------------------------------------------------------


def md_table(header: list[str], rows: list[list[Any]]) -> str:
    def clean(value: Any) -> str:
        return (
            str(value if value is not None else "-")
            .replace("|", "\\|")
            .replace("\n", " ")
        )

    lines = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    lines += ["| " + " | ".join(clean(v) for v in row) + " |" for row in rows]
    return "\n".join(lines)


def scope_statement(facts: dict) -> str:
    filters = facts["filters"]
    searched = [f"service `{s}`" for s in filters["services"]]
    if filters["stack"]:
        searched.append(f"stack `{filters['stack']}`")
    if filters["environment"]:
        searched.append(f"environment `{filters['environment']}`")
    inventory = facts["inventory"]
    repositories = repositories_of(facts)
    exists = (
        f"services: {', '.join(inventory['services']) or 'none'}; "
        f"stacks: {', '.join(inventory['stacks']) or 'none'}; "
        f"environments: {', '.join(inventory['environments']) or 'none'}"
        + (f"; repositories: {', '.join(repositories)}" if repositories else "")
    )
    return (
        f"No report matches the scope searched ({', '.join(searched)}). "
        f"The {inventory['report_count']} stored reports carry {exists}."
    )


def repositories_of(facts: dict) -> list[str]:
    """The distinct repositories the stored reports name (the whole store,
    like the inventory's services and stacks); empty when none carries one."""
    return list(facts["inventory"].get("repositories") or [])


def inventory_lines(facts: dict) -> list[str]:
    inventory = facts["inventory"]
    reports = readable(facts)
    repositories = repositories_of(facts)
    kinds = {
        k: sum(r["kind"] == k for r in reports)
        for k in ("observation", "instrumentation")
    }
    ledger = facts["ledger"]
    ledger_line = (
        f"present, {sum(r['status'] == 'ok' for r in ledger['rows'])} row(s) read, "
        f"{sum(r['status'] == 'skipped' for r in ledger['rows'])} skipped"
        if ledger["present"]
        else "absent (no decision recorded yet)"
    )
    classifications = facts.get("classifications") or {"present": False, "rows": []}
    classifications_line = (
        f"present, {sum(r['status'] == 'ok' for r in classifications['rows'])} row(s) read, "
        f"{sum(r['status'] == 'skipped' for r in classifications['rows'])} skipped"
        if classifications["present"]
        else "absent (no entry classified yet)"
    )
    head = facts["head"] or {}
    return [
        "## Inventory",
        "",
        (
            f"- Reports: {facts['matched']} matched of {inventory['report_count']} stored "
            f"({kinds['observation']} observation, {kinds['instrumentation']} instrumentation)"
        ),
        (
            f"- Services: {', '.join(inventory['services']) or 'none'}; "
            f"stacks: {', '.join(inventory['stacks']) or 'none'}; "
            f"environments: {', '.join(inventory['environments']) or 'none'}"
            + (f"; repositories: {', '.join(repositories)}" if repositories else "")
        ),
        f"- Decisions ledger: {ledger_line}",
        f"- Entry classifications: {classifications_line}",
        f"- HEAD: {str(head.get('sha', '?'))[:7]} ({str(head.get('date', '?'))[:10]})",
        "",
    ]


def invariant_section(facts: dict) -> list[str]:
    """The memory invariant: never a failure - the store is append-only."""
    invariant = facts.get("invariant") or {
        "checked": 0,
        "violations": [],
        "legacy": [],
    }
    ledger = facts["ledger"]
    skipped = [r for r in ledger["rows"] if r["status"] == "skipped"]
    classifications = facts.get("classifications") or {"present": False, "rows": []}
    skipped_classes = [r for r in classifications["rows"] if r["status"] == "skipped"]
    checked = invariant["checked"]
    legacy = invariant.get("legacy", [])
    clean = checked - len(invariant["violations"])
    out = [
        "## Memory invariant",
        "",
        (
            f"- Reports: {clean} of {checked} carry the contract's frontmatter"
            + (
                ""
                if invariant["violations"]
                else " - every stored report carries the contract's frontmatter"
            )
            + (
                f"; {len(legacy)} predate the `depth` field and read as full"
                f" ({', '.join(Path(p).name for p in legacy[:3])}"
                + (f", +{len(legacy) - 3} more" if len(legacy) > 3 else "")
                + ")"
                if legacy
                else ""
            )
        ),
        (
            f"- Decisions: {len(skipped)} row(s) skipped"
            + (
                ""
                if skipped
                else (
                    " - every decision names a stored report and a finding it carries"
                    if ledger["present"]
                    else " (no ledger yet)"
                )
            )
        ),
        (
            f"- Classifications: {len(skipped_classes)} row(s) skipped"
            + (
                ""
                if skipped_classes
                else (
                    " - every ruling names a top-level entry of HEAD and a class"
                    if classifications["present"]
                    else " (no entry classified yet)"
                )
            )
        ),
        "",
    ]
    rows: list[list[str]] = []
    for violation in invariant["violations"]:
        for problem in violation["problems"]:
            rows.append([violation["path"], problem])
    for row in skipped:
        rows.append([f"decisions.md line {row['line']}", row["reason"]])
    for row in skipped_classes:
        rows.append([f"entry-classifications.md line {row['line']}", row["reason"]])
    if rows:
        out += [
            md_table(["File", "Violation"], rows),
            "",
            (
                "The store is append-only: a report is never edited to repair it - "
                "a new run supersedes it, and a decision row is appended, never rewritten."
            ),
            "",
        ]
    return out


def state_rows(facts: dict) -> list[list[str]]:
    by_target = verifications_of(facts)
    rows = []
    for label, line in lineages(facts).items():
        observations = [r for r in line if mode_of(r) in OBSERVATION_MODES]
        verifications = [r for r in line if is_verify(r)]
        last_obs = observations[-1] if observations else None
        last_ver = verifications[-1] if verifications else None
        chain_cell = chain(line)
        if line[-1]["kind"] == "instrumentation":
            plan = line[-1]
            last_obs_cell = f"plan {name_of(plan)} ({date_of(plan)})"
            covering = verification_chain(name_of(plan), by_target)
            last_ver = covering[-1] if covering else None
            chain_cell = f"planned {date_of(plan)}"
            if last_ver:
                chain_cell += (
                    f" -> verified {date_of(last_ver)} ({verdict_label(last_ver)})"
                )
            else:
                chain_cell += " -> awaiting verification"
        elif last_obs:
            fm = last_obs["frontmatter"]
            workload = f", workload {fm.get('workload')}" if fm.get("workload") else ""
            last_obs_cell = (
                f"{date_of(last_obs)} {fm.get('run_name')} ({mode_of(last_obs)}, "
                f"depth {fm.get('depth') or 'full'}{workload})"
            )
        else:
            last_obs_cell = "none in observe mode"
        last_ver_cell = (
            f"{date_of(last_ver)} {name_of(last_ver)}: {verdict_label(last_ver)}, "
            f"verifies {last_ver['frontmatter'].get('verifies')}"
            if last_ver
            else "none yet"
        )
        rows.append(
            [
                label,
                last_obs_cell,
                last_ver_cell,
                chain_cell,
                boundary(line[-1])["evidence"],
            ]
        )
    return rows


LOOP_STATE_HEADER = [
    "Lineage",
    "Last report",
    "Open",
    "Verified",
    "Regr.",
    "Decl.",
    "Unkn.",
    "Action",
]


def render(
    facts: dict,
    today: str | date | None = None,
    *,
    full: bool = False,
    ruled: list[str] | tuple[str, ...] = (),
) -> str:
    out = ["# ODD loop status", ""]
    if not facts["loop_started"]:
        message = (
            "The loop has not started here: no report under `.odd/`. "
            "Start with `/odd-instrument-otel` or `/odd-observe`."
        )
    elif facts["matched"] == 0:
        message = scope_statement(facts)
    else:
        message = None
    if message is not None:
        out.append(message)
        if ruled:
            out.append(f"{plural(len(ruled), 'ruling')} not applied: nothing to rule.")
        return "\n".join(out) + "\n"

    # The judgment list, in five groups by what settling an item changes -
    # the order the screen's cap applies to, the full rendering's order too.
    # A lineage's boundary (settled with --runtime / --non-runtime, it flips
    # the action), the rulings the rules could not read and the ones outside
    # their chain (settled with --ruled, they move a finding between burn-down
    # columns), the verdict problems, the gap notes, and the memory hygiene
    # last: the reports, ledger rows and flags the run could not read, most
    # of them already counted on the invariant line, none of them a store
    # item to settle. A --ruled flag the renderer refused (no such finding,
    # declined by the ledger) is a ruling to correct, so it rides with the
    # rulings, not with the flags it could not parse.
    hygiene: list[str] = []
    for report in facts["reports"]:
        if "unreadable" in report:
            hygiene.append(
                f"unreadable report {report['path']}: {report['unreadable']}"
            )
    for report in readable(facts):
        for error in report.get("frontmatter_errors", []):
            hygiene.append(f"frontmatter of {name_of(report)}: {error}")
    for row in facts["ledger"]["rows"]:
        if row["status"] == "skipped":
            hygiene.append(f"ledger line {row['line']} skipped: {row['reason']}")
    for row in (facts.get("classifications") or {"rows": []})["rows"]:
        if row["status"] == "skipped":
            hygiene.append(
                f"classification line {row['line']} skipped: {row['reason']}"
            )
    verdicts: list[str] = []
    for report in readable(facts):
        if is_verify(report):
            label = verdict_label(report)
            if label == "no verdict stated":
                verdicts.append(
                    f"{name_of(report)} states no verdict and rules on nothing"
                )
            elif label.startswith("no verdict stated"):
                verdicts.append(f"{name_of(report)} states two verdicts {label[18:]}")
            coverage = quick_coverage(report)
            if coverage and coverage[0] < coverage[1]:
                verdicts.append(
                    f"quick verification {name_of(report)} ruled {coverage[0]} of "
                    f"{coverage[1]}: verified only for those items, never for the service"
                )

    rows = finding_rows(facts)
    problems, ruled_keys = apply_rulings(rows, ruled)
    hygiene += [p for p in problems if not RULING_REFUSED_RE.search(p)]
    counts = burn_down(rows)
    rulings: list[str] = []
    for r in rows:
        if r["state"] == "unknown":
            rulings.append(
                f"finding {Path(r['report']).name} / {r['id']}: "
                f"ruling not readable by rule ({r['ruled_by']})"
            )
    rulings += out_of_chain_rulings(facts, ruled_keys)
    rulings += [p for p in problems if RULING_REFUSED_RE.search(p)]

    trends, apart = trend_rows(facts)
    gaps = gap_rows(facts)
    gap_notes: list[str] = []
    for g in gaps:
        if g["gap"].startswith("(section 5 not lifted)"):
            gap_notes.append(
                f"gaps of {g['recorded_by']}: section 5 not lifted, open the body"
            )
    for name in sorted({g["recorded_by"] for g in gaps if g["truncated"]}):
        gap_notes.append(
            f"section 5 of {name} truncated: the gaps beyond the cap are unlisted"
        )
    for name in mixed_not_queried(facts):
        gap_notes.append(
            f"section 5 of {name} mixes a not-queried list with its gaps: open the body "
            "for the gaps it carries"
        )
    recs = recommendations(facts, today)
    boundaries: list[str] = []
    for r in recs:
        if r["action"] == "judgment needed":
            # the screen's row already carries the evidence: point at it
            boundaries.append(
                f"{r['lineage']}: {r['evidence']}"
                if full
                else f"{r['lineage']}: judgment needed - see its evidence under Loop state"
            )
    judgment = boundaries + rulings + verdicts + gap_notes + hygiene

    if full:
        out += inventory_lines(facts)
        out += invariant_section(facts)
    else:
        out += screen_lines(facts)
    table, evidence = loop_state_rows(
        facts, rows, recs, None if full else MAX_SCREEN_EVIDENCE
    )
    out += ["## Loop state", "", md_table(LOOP_STATE_HEADER, table), "", *evidence, ""]
    if full:
        out += full_sections(facts, rows, counts, trends, apart, gaps, recs)
    else:
        pairs = len({t["pair"] for t in trends})
        out += [
            (
                f"Not on this screen: {plural(len(rows), 'finding')}, "
                f"{plural(pairs, 'trend pair')}"
                + (f" (+{len(apart)} listed apart)" if apart else "")
                + f", {plural(len(gaps), 'gap')}, the loop state's chain and "
                "code boundary, whole items and evidence - `--full` renders them."
            ),
            "",
        ]

    out += ["## Judgment needed", ""]
    if judgment:
        items = judgment
        if not full:
            items = [cap(i, MAX_SCREEN_ITEM)[0] for i in judgment[:MAX_SCREEN_ITEMS]]
            if len(judgment) > MAX_SCREEN_ITEMS:
                items.append(f"+{len(judgment) - MAX_SCREEN_ITEMS} more - `--full`")
        out += [f"- {item}" for item in items]
    else:
        out.append("- nothing deferred: every row above follows from a rule")
    return "\n".join(out) + "\n"


def full_sections(
    facts: dict,
    rows: list[dict],
    counts: dict[str, int],
    trends: list[dict],
    apart: list[dict],
    gaps: list[dict],
    recs: list[dict],
) -> list[str]:
    """The working tables: loop state, ledger, trends, gaps, next action."""
    out = [
        "## Per-service loop state",
        "",
        md_table(
            [
                "Lineage",
                "Last observation",
                "Last verification",
                "Chain",
                "Code since last report",
            ],
            state_rows(facts),
        ),
        "",
    ]
    burn = " · ".join(f"{s} {counts[s]}" for s in STATES[:4])
    if counts["unknown"]:
        burn += f" · unknown {counts['unknown']}"
    out += ["## Findings ledger", "", f"Burn-down: {burn}.", ""]
    if rows:
        table_rows = []
        for r in rows:
            key = f"{Path(r['report']).name} / {r['id']}"
            ruled_by = cap(r["ruled_by"], MAX_RULED_BY)[0]
            table_rows.append([key, r["title"], r["severity"], r["state"], ruled_by])
        out += [
            md_table(
                ["Report / ID", "Finding", "Severity", "State", "Ruled by"], table_rows
            ),
            "",
        ]
    else:
        out += ["No finding recorded.", ""]

    out += [
        "## Trends",
        "",
        (
            f"Rule: regressed when the error rate moves by more than {ERROR_THRESHOLD:g} "
            f"points, else by the latency metric (p95 when both carry one): stable within "
            f"{LATENCY_FLOOR:g} ms or {TREND_THRESHOLD:.0%}, improved or regressed beyond; "
            "n/a when a cell is not a bare measurement."
        ),
        "",
    ]
    if trends:
        pairs: dict[str, list[dict]] = {}
        for t in trends:
            pairs.setdefault(t["pair"], []).append(t)
        for pair, group in pairs.items():
            out += [
                f"Pair {pair}:",
                "",
                md_table(
                    ["Operation", "p50", "p95", "p99", "Error", "Trend"],
                    [
                        [
                            t["operation"],
                            t["p50"],
                            t["p95"],
                            t["p99"],
                            t["error"],
                            t["trend"],
                        ]
                        for t in group
                    ],
                ),
                "",
            ]
    else:
        out += ["No verifies pair to compare.", ""]
    if apart:
        out += ["Listed apart, not compared by rule (information, not a deferral):", ""]
        out += [
            f"- {a['reports'][0]} and {a['reports'][1]}: {a['reason']}" for a in apart
        ]
        out.append("")

    out += ["## Open telemetry gaps", ""]
    if gaps:
        out += [
            md_table(
                ["Lineage", "Gap (as last recorded)", "Recorded by"],
                [[g["lineage"], g["gap"], g["recorded_by"]] for g in gaps],
            ),
            "",
        ]
    elif mixed_not_queried(facts):
        out += ["No gap listed by rule - see Judgment needed.", ""]
    else:
        out += ["No gap recorded.", ""]

    out += [
        "## Next recommended action",
        "",
        md_table(
            ["Lineage", "Action", "Evidence"],
            [[r["lineage"], r["action"], r["evidence"]] for r in recs],
        ),
        "",
    ]
    return out
