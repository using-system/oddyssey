#!/usr/bin/env bash
# Regenerate the native marketplace artifacts from the APM package:
#   .claude-plugin/marketplace.json   (Claude Code, Copilot CLI, Kimi Code)
#   .agents/plugins/marketplace.json  (Codex)
#   marketplace/oddyssey/             (the materialized plugin the manifests
#                                      point at: agents, commands, skills,
#                                      .claude-plugin/plugin.json, .mcp.json)
# Everything it writes is GENERATED - never edit those files by hand.
# Run by the release workflow after the version bumps, so the artifacts
# always carry the released version and the matching oddyssey-mcp pin.
set -euo pipefail

APM_CLI_VERSION="${APM_CLI_VERSION:-0.28.0}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

MCP_PIN="$(grep -o 'oddyssey-mcp==[0-9][0-9.]*' apm.yml | head -1)"
if [ -z "$MCP_PIN" ]; then
  echo "could not read the oddyssey-mcp pin from apm.yml" >&2
  exit 1
fi

# One pack builds the plugin bundle (into a temp dir, in a versioned
# subdirectory) AND rewrites both marketplace manifests at their fixed
# root locations.
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
uvx --from "apm-cli==${APM_CLI_VERSION}" apm pack --target claude -o "$TMP"

# Flatten the versioned bundle into the stable path the manifests
# reference (marketplace/oddyssey), with the plugin manifest where
# Claude Code expects it.
rm -rf marketplace/oddyssey
mkdir -p marketplace/oddyssey/.claude-plugin
cp -R "$TMP"/oddyssey-*/. marketplace/oddyssey/
mv marketplace/oddyssey/plugin.json marketplace/oddyssey/.claude-plugin/plugin.json

# apm pack does not carry the MCP dependency into the plugin bundle;
# inject it so a native install gets the stack-piloting server too,
# pinned to the same version apm.yml pins.
cat > marketplace/oddyssey/.mcp.json <<EOF
{
  "mcpServers": {
    "oddyssey": {
      "type": "stdio",
      "command": "uvx",
      "args": ["${MCP_PIN}"]
    }
  }
}
EOF

cat > marketplace/README.md <<'EOF'
# GENERATED - do not edit

Everything under this directory (and the manifests at
`.claude-plugin/marketplace.json` and `.agents/plugins/marketplace.json`)
is generated from the APM package by `scripts/build-marketplace.sh`,
which the release workflow runs after every version bump. Edit the
sources under `.apm/` and `apm.yml` instead.
EOF

echo "marketplace artifacts regenerated (${MCP_PIN})"
