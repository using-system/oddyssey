"""Global oddyssey configuration: one file per machine, like the stack.

One shared container for every project on the machine is the assumed
design (#50 closed not-planned), so the configuration is global too -
user scope, no per-project state. The file is hand-editable: reads are
tolerant (a broken value degrades to its default, visibly), writes are
strict (a rejected partial writes nothing).
"""

from __future__ import annotations

import json
from pathlib import Path

CONFIG_PATH = Path.home() / ".oddyssey" / "config.json"

# The backends of the observability-cli-guides skill. No "local" value:
# local IS grafana - the specificity lives in the setup-local-stack skill.
STACKS = ("grafana", "azure-monitor", "cloudwatch", "datadog", "dynatrace", "splunk")

DEFAULTS = {
    "stack": "grafana",
    "local": {"grafana_port": 3000, "otlp_grpc_port": 4317, "otlp_http_port": 4318},
}


def _valid_port(value: object) -> bool:
    return (
        isinstance(value, int) and not isinstance(value, bool) and 1 <= value <= 65535
    )


def load(path: Path | None = None) -> dict:
    """Effective configuration: defaults overlaid with the stored file.

    Tolerant by contract - the file is hand-editable and a tool call
    must never crash on it. Every tolerated-invalid field is listed in
    "invalid_ignored" (dotted names; "<file>" for unparseable JSON) so
    odd_config_get can surface the degradation.
    """
    target = CONFIG_PATH if path is None else path
    effective = {"stack": DEFAULTS["stack"], "local": dict(DEFAULTS["local"])}
    invalid: list[str] = []
    try:
        stored = json.loads(target.read_text())
    except FileNotFoundError:
        return effective
    except (OSError, ValueError):
        effective["invalid_ignored"] = ["<file>"]
        return effective
    if not isinstance(stored, dict):
        effective["invalid_ignored"] = ["<file>"]
        return effective

    stack = stored.get("stack", DEFAULTS["stack"])
    if stack in STACKS:
        effective["stack"] = stack
    else:
        invalid.append("stack")

    local = stored.get("local", {})
    if isinstance(local, dict):
        for key in DEFAULTS["local"]:
            if key not in local:
                continue
            if _valid_port(local[key]):
                effective["local"][key] = local[key]
            else:
                invalid.append(f"local.{key}")
    elif "local" in stored:
        invalid.append("local")

    if invalid:
        effective["invalid_ignored"] = invalid
    return effective
