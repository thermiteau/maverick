#!/usr/bin/env bash
set -euo pipefail

# Integration test scaffolding for the multi-instance coordination layer.
#
# What this verifies:
#   - The maverick CLI exposes the coord / dag / state / worktree / gh-app / gh-state
#     subcommands and their arguments.
#   - Help messages print cleanly for every leaf subcommand.
#   - `gh-app status` runs and reports missing config without crashing.
#
# What this does NOT verify (requires a sandbox GH repo + Maverick GitHub App):
#   - claim / heartbeat / release against a real issue.
#   - DAG + state marker round-trips against a real epic.
#   - Takeover of a stale lease by a second instance.
#
# When the user wants full chaos-mode coverage:
#   1. Create a throwaway GH repo and a test epic issue with ≥ 3 child stories.
#   2. Set MAVERICK_TEST_REPO=owner/repo and MAVERICK_TEST_EPIC=<issue-number>.
#   3. Extend this script with the commented-out blocks marked `# TODO`.
#
# The scaffolding here is the harness; the real workflow exercise is a
# follow-on. It exists so WP14's intent is on disk even while the chaos
# tests are still a manual exercise.

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"

pass() { echo "  PASS: $1"; }
fail() { echo "  FAIL: $1"; exit 1; }

cd "$REPO_ROOT"

# ── CLI surface tests ────────────────────────────────────────────────────────

echo "=== CLI surface tests ==="

uv run maverick --help >/dev/null 2>&1 || fail "top-level --help exited non-zero"
pass "top-level --help"

for sub in coord dag state worktree gh-app gh-state; do
    uv run maverick "$sub" --help >/dev/null 2>&1 \
        || fail "'$sub --help' failed"
    pass "'$sub --help'"
done

# ── Leaf-command arg parsing ─────────────────────────────────────────────────

echo "=== Leaf-command arg parsing ==="

for leaf in "coord read" "coord claim" "coord heartbeat" "coord release" \
            "coord takeover" "dag show" "dag waves" "dag descendants" \
            "state show" "state set" "worktree create" "worktree list" \
            "worktree destroy" "gh-state read"; do
    uv run maverick $leaf --help >/dev/null 2>&1 \
        || fail "'$leaf --help' failed"
    pass "'$leaf --help'"
done

# ── gh-app status ────────────────────────────────────────────────────────────

echo "=== gh-app status ==="

status_output="$(uv run maverick gh-app status 2>&1)"
echo "$status_output" | grep -q '"configured"' \
    || fail "gh-app status output missing 'configured' key: $status_output"
pass "gh-app status returns JSON with 'configured' key"

# ── Live-GH scenarios (skipped unless env set) ───────────────────────────────

if [[ -n "${MAVERICK_TEST_REPO:-}" && -n "${MAVERICK_TEST_EPIC:-}" ]]; then
    echo "=== Live-GH scenarios ==="
    echo "  (MAVERICK_TEST_REPO=$MAVERICK_TEST_REPO, MAVERICK_TEST_EPIC=$MAVERICK_TEST_EPIC)"

    # TODO: claim, heartbeat, release round-trip on a test issue
    # TODO: DAG write + read round-trip on the test epic
    # TODO: state transition + mirror-to-GH verification
    # TODO: takeover of a manually-staled lease
    # TODO: block propagation across a known DAG

    echo "  (live scenarios not yet implemented — placeholder TODOs in this script)"
else
    echo "=== Live-GH scenarios SKIPPED ==="
    echo "  Set MAVERICK_TEST_REPO=owner/repo and MAVERICK_TEST_EPIC=<n> to run."
fi

echo ""
echo "All coordination surface tests passed."
