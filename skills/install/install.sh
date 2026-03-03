#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLUGIN_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

# --- 1. Check uv is available ---

if ! command -v uv &>/dev/null; then
  echo "Error: uv is required but not installed." >&2
  echo "Install it with:  curl -LsSf https://astral.sh/uv/install.sh | sh" >&2
  exit 1
fi

# --- 2. Check pyproject.toml exists ---

if [[ ! -f "$PLUGIN_ROOT/pyproject.toml" ]]; then
  echo "Error: pyproject.toml not found at $PLUGIN_ROOT" >&2
  echo "This script must be run from a complete maverick plugin directory." >&2
  exit 1
fi

# --- 3. Install the CLI ---

echo "Installing maverick CLI from $PLUGIN_ROOT ..."
uv tool install --force "$PLUGIN_ROOT"

# --- 4. Verify maverick is on PATH ---

if command -v maverick &>/dev/null; then
  echo "maverick installed successfully: $(command -v maverick)"
else
  echo ""
  echo "Warning: maverick was installed but is not on your PATH." >&2
  echo "Add ~/.local/bin to your PATH:" >&2
  echo '  export PATH="$HOME/.local/bin:$PATH"' >&2
  echo ""
  echo "Then restart your shell or run the export command above." >&2
fi

# --- 5. Update ~/.claude/settings.json permissions ---

SETTINGS_FILE="$HOME/.claude/settings.json"
PERM_ENTRY="Read(~/.claude/plugins/cache/thermite/maverick/**)"

update_permissions() {
  python3 -c "
import json, sys
from pathlib import Path

settings_path = Path('$SETTINGS_FILE')

if settings_path.exists():
    settings = json.loads(settings_path.read_text())
else:
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    settings = {}

permissions = settings.setdefault('permissions', {})
allow = list(permissions.get('allow', []))

entry = '$PERM_ENTRY'
if entry not in allow:
    allow.append(entry)
    permissions['allow'] = allow
    permissions.setdefault('deny', [])
    settings['permissions'] = permissions
    settings_path.write_text(json.dumps(settings, indent=2) + '\n')
    print('Updated ' + str(settings_path) + ' with read permission for plugin cache.')
else:
    print('Permission already present in ' + str(settings_path) + '.')
"
}

update_permissions

echo ""
echo "Done."
