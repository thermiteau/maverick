#!/usr/bin/env bash
set -euo pipefail

# Integration tests for the maverick CLI.
# Runs real CLI commands end-to-end. Exits non-zero on first failure.

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
TMPDIR_BASE=""
SETTINGS_FILE="$HOME/.claude/settings.json"
SETTINGS_BACKUP=""

# ── helpers ──────────────────────────────────────────────────────────────────

pass() { echo "  PASS: $1"; }
fail() { echo "  FAIL: $1"; exit 1; }

cleanup() {
    [[ -n "$TMPDIR_BASE" && -d "$TMPDIR_BASE" ]] && rm -rf "$TMPDIR_BASE"
    if [[ -n "$SETTINGS_BACKUP" && -f "$SETTINGS_BACKUP" ]]; then
        cp "$SETTINGS_BACKUP" "$SETTINGS_FILE"
        rm -f "$SETTINGS_BACKUP"
    elif [[ -n "$SETTINGS_BACKUP" ]]; then
        # Original didn't exist — remove whatever we created
        rm -f "$SETTINGS_FILE"
        rm -f "$SETTINGS_BACKUP"
    fi
}
trap cleanup EXIT

# Back up settings.json before any test touches it
if [[ -f "$SETTINGS_FILE" ]]; then
    SETTINGS_BACKUP="$(mktemp)"
    cp "$SETTINGS_FILE" "$SETTINGS_BACKUP"
else
    # Marker so cleanup knows the file didn't exist originally
    SETTINGS_BACKUP="$(mktemp)"
    rm -f "$SETTINGS_BACKUP"          # file won't exist — signals "no original"
    SETTINGS_BACKUP="$SETTINGS_BACKUP" # keep the path for the flag
fi

TMPDIR_BASE="$(mktemp -d)"

# ── tests ────────────────────────────────────────────────────────────────────

test_uv_tool_install() {
    echo "TEST: uv tool install"
    uv tool install --force "$REPO_ROOT" \
        || fail "uv tool install exited non-zero"
    maverick --help >/dev/null 2>&1 \
        || fail "maverick --help not available after install"
    pass "uv tool install"
}

test_init() {
    echo "TEST: maverick init"
    local project_dir="$TMPDIR_BASE/test-project"
    mkdir -p "$project_dir"
    # Drop a pyproject.toml so detection has something to find
    echo '[project]' > "$project_dir/pyproject.toml"
    (cd "$project_dir" && maverick init) \
        || fail "maverick init exited non-zero"
    [[ -f "$project_dir/.maverick/config.toml" ]] \
        || fail ".maverick/config.toml not created"
    pass "maverick init"
}

test_plugin_install_dev() {
    echo "TEST: maverick plugin install --dev"
    (cd "$REPO_ROOT" && maverick plugin install --dev) \
        || fail "maverick plugin install --dev exited non-zero"
    grep -q "maverick-plugin" "$SETTINGS_FILE" \
        || fail "settings.json does not contain maverick-plugin"
    pass "maverick plugin install --dev"
}

test_plugin_uninstall() {
    echo "TEST: maverick plugin uninstall"
    maverick plugin uninstall \
        || fail "maverick plugin uninstall exited non-zero"
    if grep -q '"pluginDirs"' "$SETTINGS_FILE" 2>/dev/null; then
        fail "pluginDirs still present in settings.json"
    fi
    pass "maverick plugin uninstall"
}

test_clean_dry_run() {
    echo "TEST: maverick clean --dry-run"
    local project_dir="$TMPDIR_BASE/test-project"
    (cd "$project_dir" && maverick clean --dry-run) \
        || fail "maverick clean --dry-run exited non-zero"
    # Artifacts should still exist after dry-run
    [[ -d "$project_dir/.maverick" ]] \
        || fail ".maverick removed despite --dry-run"
    pass "maverick clean --dry-run"
}

# ── run ──────────────────────────────────────────────────────────────────────

echo "=== Maverick CLI Integration Tests ==="
echo ""
test_uv_tool_install
test_init
test_plugin_install_dev
test_plugin_uninstall
test_clean_dry_run
echo ""
echo "All tests passed."
