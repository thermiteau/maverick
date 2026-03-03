#!/usr/bin/env bash
set -euo pipefail

# Integration tests that clone real public repos and run maverick commands.
# Validates stack detection, init, clean, and plugin workflows against
# real-world project structures.

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
TMPDIR_BASE=""
SETTINGS_FILE="$HOME/.claude/settings.json"
SETTINGS_BACKUP=""
TEST_COUNT=0
PASS_COUNT=0

# ── helpers ──────────────────────────────────────────────────────────────────

pass() { PASS_COUNT=$((PASS_COUNT + 1)); echo "  PASS: $1"; }
fail() { echo "  FAIL: $1"; exit 1; }

cleanup() {
    [[ -n "$TMPDIR_BASE" && -d "$TMPDIR_BASE" ]] && rm -rf "$TMPDIR_BASE"
    if [[ -n "$SETTINGS_BACKUP" && -f "$SETTINGS_BACKUP" ]]; then
        cp "$SETTINGS_BACKUP" "$SETTINGS_FILE"
        rm -f "$SETTINGS_BACKUP"
    elif [[ -n "$SETTINGS_BACKUP" ]]; then
        rm -f "$SETTINGS_FILE"
        rm -f "$SETTINGS_BACKUP"
    fi
}
trap cleanup EXIT

# Back up settings.json
if [[ -f "$SETTINGS_FILE" ]]; then
    SETTINGS_BACKUP="$(mktemp)"
    cp "$SETTINGS_FILE" "$SETTINGS_BACKUP"
else
    SETTINGS_BACKUP="$(mktemp)"
    rm -f "$SETTINGS_BACKUP"
    SETTINGS_BACKUP="$SETTINGS_BACKUP"
fi

TMPDIR_BASE="$(mktemp -d)"

# ── shared test functions ────────────────────────────────────────────────────

clone_repo() {
    local url="$1" name="$2"
    local dest="$TMPDIR_BASE/$name"
    echo "  Cloning $url (shallow)..." >&2
    git clone --depth 1 --quiet "$url" "$dest" \
        || fail "git clone $url failed"
    echo "$dest"
}

# Assert a module appears in the config.toml active list
assert_module_detected() {
    local config_file="$1" module="$2"
    grep -q "\"$module\"" "$config_file" \
        || fail "expected module '$module' not found in config.toml"
}

# Assert a module does NOT appear in the config.toml active list
assert_module_not_detected() {
    local config_file="$1" module="$2"
    if grep -q "\"$module\"" "$config_file"; then
        fail "unexpected module '$module' found in config.toml"
    fi
}

# ── per-repo test suites ────────────────────────────────────────────────────

# Each test_repo_* function clones a repo and runs a series of maverick
# commands against it, validating detection and lifecycle.

test_repo_js_service_manual() {
    echo ""
    echo "── govau/service-manual (JavaScript) ──"
    local project_dir
    project_dir=$(clone_repo "https://github.com/govau/service-manual.git" "service-manual")
    local config="$project_dir/.maverick/config.toml"

    # init --dry-run: no files written
    TEST_COUNT=$((TEST_COUNT + 1))
    echo "TEST: init --dry-run"
    (cd "$project_dir" && maverick init --dry-run) \
        || fail "maverick init --dry-run exited non-zero"
    [[ ! -f "$config" ]] \
        || fail "config.toml created despite --dry-run"
    pass "init --dry-run"

    # init: detect nodejs
    TEST_COUNT=$((TEST_COUNT + 1))
    echo "TEST: init (detect nodejs)"
    (cd "$project_dir" && maverick init) \
        || fail "maverick init exited non-zero"
    [[ -f "$config" ]] \
        || fail "config.toml not created"
    assert_module_detected "$config" "nodejs"
    assert_module_not_detected "$config" "python"
    pass "init (detect nodejs)"

    # init --add: add a module
    TEST_COUNT=$((TEST_COUNT + 1))
    echo "TEST: init --add docker"
    (cd "$project_dir" && maverick init --add docker) \
        || fail "maverick init --add docker exited non-zero"
    assert_module_detected "$config" "docker"
    assert_module_detected "$config" "nodejs"
    pass "init --add docker"

    # init --remove: remove a module
    TEST_COUNT=$((TEST_COUNT + 1))
    echo "TEST: init --remove docker"
    (cd "$project_dir" && maverick init --remove docker) \
        || fail "maverick init --remove docker exited non-zero"
    assert_module_not_detected "$config" "docker"
    assert_module_detected "$config" "nodejs"
    pass "init --remove docker"

    # plugin install --dev from repo root (not from cloned repo)
    TEST_COUNT=$((TEST_COUNT + 1))
    echo "TEST: plugin install --dev"
    (cd "$REPO_ROOT" && maverick plugin install --dev) \
        || fail "maverick plugin install --dev exited non-zero"
    grep -q "maverick-plugin" "$SETTINGS_FILE" \
        || fail "settings.json does not contain maverick-plugin"
    pass "plugin install --dev"

    # plugin uninstall
    TEST_COUNT=$((TEST_COUNT + 1))
    echo "TEST: plugin uninstall"
    maverick plugin uninstall \
        || fail "maverick plugin uninstall exited non-zero"
    if grep -q '"pluginDirs"' "$SETTINGS_FILE" 2>/dev/null; then
        fail "pluginDirs still present after uninstall"
    fi
    pass "plugin uninstall"

    # clean --dry-run: artifacts survive
    TEST_COUNT=$((TEST_COUNT + 1))
    echo "TEST: clean --dry-run"
    (cd "$project_dir" && maverick clean --dry-run) \
        || fail "maverick clean --dry-run exited non-zero"
    [[ -d "$project_dir/.maverick" ]] \
        || fail ".maverick removed despite --dry-run"
    pass "clean --dry-run"

    # clean: artifacts removed
    TEST_COUNT=$((TEST_COUNT + 1))
    echo "TEST: clean"
    (cd "$project_dir" && maverick clean) \
        || fail "maverick clean exited non-zero"
    [[ ! -d "$project_dir/.maverick" ]] \
        || fail ".maverick still exists after clean"
    pass "clean"
}

test_repo_python_sampleproject() {
    echo ""
    echo "── data61/blocklib (Python) ──"
    local project_dir
    project_dir=$(clone_repo "https://github.com/data61/blocklib.git" "blocklib")
    local config="$project_dir/.maverick/config.toml"

    # init: detect python
    TEST_COUNT=$((TEST_COUNT + 1))
    echo "TEST: init (detect python)"
    (cd "$project_dir" && maverick init) \
        || fail "maverick init exited non-zero"
    [[ -f "$config" ]] \
        || fail "config.toml not created"
    assert_module_detected "$config" "python"
    assert_module_not_detected "$config" "nodejs"
    pass "init (detect python)"

    # init is idempotent: run again, should overwrite without error
    TEST_COUNT=$((TEST_COUNT + 1))
    echo "TEST: init idempotent"
    (cd "$project_dir" && maverick init) \
        || fail "maverick init (second run) exited non-zero"
    assert_module_detected "$config" "python"
    pass "init idempotent"

    # init --override: replace detected modules entirely
    TEST_COUNT=$((TEST_COUNT + 1))
    echo "TEST: init --override nodejs docker"
    (cd "$project_dir" && maverick init --override nodejs docker) \
        || fail "maverick init --override exited non-zero"
    assert_module_detected "$config" "nodejs"
    assert_module_detected "$config" "docker"
    assert_module_not_detected "$config" "python"
    pass "init --override nodejs docker"

    # init --platform: set cloud platform
    TEST_COUNT=$((TEST_COUNT + 1))
    echo "TEST: init --platform aws"
    (cd "$project_dir" && maverick init --platform aws) \
        || fail "maverick init --platform exited non-zero"
    grep -q 'name = "aws"' "$config" \
        || fail "platform aws not found in config.toml"
    pass "init --platform aws"

    # clean
    TEST_COUNT=$((TEST_COUNT + 1))
    echo "TEST: clean"
    (cd "$project_dir" && maverick clean) \
        || fail "maverick clean exited non-zero"
    [[ ! -d "$project_dir/.maverick" ]] \
        || fail ".maverick still exists after clean"
    pass "clean"
}

test_repo_typescript_expressjs() {
    echo ""
    echo "── govau/observatory-website (TypeScript / Node.js) ──"
    local project_dir
    project_dir=$(clone_repo "https://github.com/govau/observatory-website.git" "observatory-website")
    local config="$project_dir/.maverick/config.toml"

    # init: detect nodejs (and possibly github-actions)
    TEST_COUNT=$((TEST_COUNT + 1))
    echo "TEST: init (detect nodejs)"
    (cd "$project_dir" && maverick init) \
        || fail "maverick init exited non-zero"
    [[ -f "$config" ]] \
        || fail "config.toml not created"
    assert_module_detected "$config" "nodejs"
    assert_module_not_detected "$config" "python"
    pass "init (detect nodejs)"

    # clean --dry-run then clean
    TEST_COUNT=$((TEST_COUNT + 1))
    echo "TEST: clean --dry-run then clean"
    (cd "$project_dir" && maverick clean --dry-run) \
        || fail "maverick clean --dry-run exited non-zero"
    [[ -d "$project_dir/.maverick" ]] \
        || fail ".maverick removed despite --dry-run"
    (cd "$project_dir" && maverick clean) \
        || fail "maverick clean exited non-zero"
    [[ ! -d "$project_dir/.maverick" ]] \
        || fail ".maverick still exists after clean"
    pass "clean --dry-run then clean"
}

# ── run ──────────────────────────────────────────────────────────────────────

echo "=== Maverick Real-Repo Integration Tests ==="

# Ensure maverick is installed
echo ""
echo "── Setup ──"
echo "TEST: uv tool install"
uv tool install --force "$REPO_ROOT" \
    || fail "uv tool install exited non-zero"
maverick --help >/dev/null 2>&1 \
    || fail "maverick --help not available after install"
TEST_COUNT=$((TEST_COUNT + 1))
pass "uv tool install"

test_repo_js_service_manual
test_repo_python_sampleproject
test_repo_typescript_expressjs

echo ""
echo "All $PASS_COUNT/$TEST_COUNT tests passed."
