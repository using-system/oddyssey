#!/usr/bin/env bash
# Regenerate the native marketplace artifacts from the APM package:
#   .claude-plugin/marketplace.json   (Claude Code, Copilot CLI, Kimi Code)
#   .agents/plugins/marketplace.json  (Codex)
#   marketplace/oddyssey/             (the materialized plugin the manifests
#                                      point at: agents, commands, skills,
#                                      plugin.json, .claude-plugin/plugin.json,
#                                      .mcp.json, mcp.json, com.github.copilot/,
#                                      LICENSE, SECURITY.md)
# Everything it writes is GENERATED - never edit those files by hand.
# Run by the release workflow after the version bumps, so the artifacts
# always carry the released version and the matching oddyssey-mcp pin.
set -euo pipefail

APM_CLI_VERSION="${APM_CLI_VERSION:-0.31.0}"
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
uvx --from "apm-cli==${APM_CLI_VERSION}" apm pack -o "$TMP"

# Flatten the versioned bundle into the stable path the manifests
# reference (marketplace/oddyssey). The one plugin.json apm pack
# synthesises becomes two manifests, at the two places the hosts read:
#   plugin.json                 - the Agent Plugins v1.0.0 location, the one
#                                 the Copilot marketplace intake and its
#                                 install smoke test look up (issue #570):
#                                 the spec's $schema first, then only the
#                                 spec's top-level fields, whitelisted so a
#                                 later apm-cli cannot leak one in
#                                 (displayName is not one - the intake
#                                 flags it);
#   .claude-plugin/plugin.json  - the Claude Code location, displayName
#                                 injected for the `/plugin` picker.
rm -rf marketplace/oddyssey
mkdir -p marketplace/oddyssey/.claude-plugin
cp -R "$TMP"/oddyssey-*/. marketplace/oddyssey/
cp marketplace/oddyssey/plugin.json "$TMP/plugin.json.packed"
jq '{"$schema": "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json"}
    + ({name, version, description, author, homepage, repository, license, keywords}
       | with_entries(select(.value != null)))' \
  "$TMP/plugin.json.packed" > marketplace/oddyssey/plugin.json

# apm-cli's plugin.json synthesis carries name/version/description/
# license/homepage/repository/author/keywords from apm.yml's root, but drops
# displayName (undocumented in its synthesizer); inject it by hand so the
# `/plugin` picker shows a human-readable name instead of the package slug.
DISPLAY_NAME="$(grep -m1 '^displayName:' apm.yml | cut -d':' -f2- | sed 's/^[[:space:]]*//')"
jq --arg name "$DISPLAY_NAME" '. + (if $name == "" then {} else {displayName: $name} end)' \
  "$TMP/plugin.json.packed" > marketplace/oddyssey/.claude-plugin/plugin.json

# apm pack does not carry the MCP dependency into the plugin bundle;
# inject it so a native install gets the stack-piloting server too,
# pinned to the same version apm.yml pins.
# Twice, at the two places the hosts read: .mcp.json is the Claude Code
# location; mcp.json is the Agent Plugins v1.0.0 one, the only file a
# client that honours plugin.json's $schema reads for servers (issue #588).
cat > marketplace/oddyssey/.mcp.json <<EOF
{
  "mcpServers": {
    "oddyssey": {
      "type": "stdio",
      "command": "uvx",
      "args": ["--refresh-package", "oddyssey-mcp", "${MCP_PIN}"]
    }
  }
}
EOF
cat > marketplace/oddyssey/mcp.json <<EOF
{
  "\$schema": "https://agent-plugins.org/schemas/1.0.0/mcp.schema.json",
  "mcpServers": {
    "oddyssey": {
      "type": "stdio",
      "command": "uvx",
      "args": ["--refresh-package", "oddyssey-mcp", "${MCP_PIN}"]
    }
  }
}
EOF

# apm pack writes the hooks as a root-level hooks.json with the commands
# unrewritten (./scripts/...) and copies no script; a Claude Code or Codex
# plugin reads hooks/hooks.json and reaches bundled files through
# ${CLAUDE_PLUGIN_ROOT}. Move the file, carry the scripts, rewrite the
# paths, and refuse a bundle that names a script it does not carry.
if [ -f marketplace/oddyssey/hooks.json ]; then
  mkdir -p marketplace/oddyssey/hooks
  sed 's#\("command":[[:space:]]*"[^"]*\)\./scripts/#\1\\"${CLAUDE_PLUGIN_ROOT}\\"/hooks/scripts/#g' \
    marketplace/oddyssey/hooks.json > marketplace/oddyssey/hooks/hooks.json
  rm marketplace/oddyssey/hooks.json
  if grep -q '\./scripts/' marketplace/oddyssey/hooks/hooks.json; then
    echo "hooks/hooks.json still names a relative script path" >&2
    exit 1
  fi
  if [ -d .apm/hooks/scripts ]; then
    cp -R .apm/hooks/scripts marketplace/oddyssey/hooks/scripts
    find marketplace/oddyssey/hooks/scripts -name __pycache__ -type d -prune -exec rm -rf {} +
  fi
  for script in $(grep -o '/hooks/scripts/[^" ]*' marketplace/oddyssey/hooks/hooks.json | sort -u); do
    if [ ! -f "marketplace/oddyssey${script}" ]; then
      echo "hooks/hooks.json names a script the bundle does not carry: ${script}" >&2
      exit 1
    fi
  done
fi

# Copilot CLI honours plugin.json's Agent Plugins $schema and then reads its
# own components from the com.github.copilot/ extension namespace only -
# commands (translated into skills), agents and hooks at the plugin root
# are "no longer read" (issue #588; the spec keeps skills/ and mcp.json
# portable, everything else client-namespaced). Mirror the three there:
# the same agent and command files, and the hooks in Copilot's dialect
# (version 1, camelCase events, scripts reached through the spec's
# ${PLUGIN_ROOT}, which Copilot resolves to the plugin root).
NS="marketplace/oddyssey/com.github.copilot"
rm -rf "$NS"
mkdir -p "$NS"
for kind in agents commands; do
  if [ -d "marketplace/oddyssey/${kind}" ]; then
    cp -R "marketplace/oddyssey/${kind}" "${NS}/${kind}"
  fi
done
if [ -f marketplace/oddyssey/hooks/hooks.json ]; then
  mkdir -p "${NS}/hooks"
  jq '{version: 1,
       hooks: (.hooks | with_entries(.key |= ((.[0:1] | ascii_downcase) + .[1:])))}' \
    marketplace/oddyssey/hooks/hooks.json \
    | sed 's#\\"${CLAUDE_PLUGIN_ROOT}\\"/hooks/scripts/#\\"${PLUGIN_ROOT}\\"/com.github.copilot/hooks/scripts/#g' \
    > "${NS}/hooks/hooks.json"
  if grep -q 'CLAUDE_PLUGIN_ROOT' "${NS}/hooks/hooks.json"; then
    echo "com.github.copilot/hooks/hooks.json still names the Claude plugin root" >&2
    exit 1
  fi
  cp -R marketplace/oddyssey/hooks/scripts "${NS}/hooks/scripts"
  for script in $(grep -o '/com.github.copilot/hooks/scripts/[^" ]*' "${NS}/hooks/hooks.json" | sort -u); do
    if [ ! -f "marketplace/oddyssey${script}" ]; then
      echo "com.github.copilot/hooks/hooks.json names a script the bundle does not carry: ${script}" >&2
      exit 1
    fi
  done
fi

# Claude Code's default, declared for the plugin scanners that want it
# explicit: the plugin's own plugin.json is the authority. On every entry,
# where Claude Code reads it, and at the root, where the HOL scanner looks
# (Claude Code ignores it there).
jq '. + {strict: true} | .plugins |= map(. + {strict: true})' .claude-plugin/marketplace.json \
  > "$TMP/marketplace.json"
cp "$TMP/marketplace.json" .claude-plugin/marketplace.json

# A scanner reads the plugin directory as a repository of its own: carry
# the repository's license and security policy into it.
cp LICENSE SECURITY.md marketplace/oddyssey/

cat > marketplace/README.md <<'EOF'
# GENERATED - do not edit

Everything under this directory (and the manifests at
`.claude-plugin/marketplace.json` and `.agents/plugins/marketplace.json`)
is generated from the APM package by `scripts/build-marketplace.sh`,
which the release workflow runs after every version bump. Edit the
sources under `.apm/` and `apm.yml` instead.
EOF

# The release does not commit this tree straight from the job that
# builds it: it travels through actions/upload-artifact, which zips the
# files and hands every one of them back as 644 (the action documents
# the loss). So the committed bundle carries no executable bit, while a
# local run inherits 755 from the sources apm pack copied - four skill
# scripts show up as mode-only modifications on a clean clone. Strip the
# bit here so both paths produce the same tree: nothing in the bundle is
# ever run through its shebang, every script is invoked as
# `python3 <script>`.
find marketplace -type f -exec chmod a-x {} +
chmod a-x .claude-plugin/marketplace.json .agents/plugins/marketplace.json

echo "marketplace artifacts regenerated (${MCP_PIN})"
