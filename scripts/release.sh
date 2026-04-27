#!/usr/bin/env bash
set -euo pipefail

# Release script for maverick — LOCAL PREP PHASE
#
# This script handles the local portion of the release process:
#   1. Create release/<version> branch from main
#   2. Bump version, update changelog, rebuild — commit on release branch
#   3. Push release branch and create a PR targeting main
#
# After the PR is squash-merged, the `release-finalize.yml` GitHub Actions
# workflow automatically handles:
#   - Tagging the squash commit on main
#   - Creating the GitHub Release
#   - Opening a follow-up PR that bumps main to the next -dev version
#
# Usage: ./scripts/release.sh [major|minor|patch]
# Default: patch
#
# Version semantics:
#   - "X.Y.Z-dev" means "in development for the X.Y.Z release". The base is
#     the target version. `release.sh patch` from "X.Y.Z-dev" produces "X.Y.Z"
#     (graduates the dev cycle); minor/major from a -dev version skip the
#     in-flight patch (e.g. patch from 1.0.2-dev -> 1.0.2 but minor -> 1.1.0).
#   - "X.Y.Z" with no suffix means the previous release was X.Y.Z. Patch then
#     increments (e.g. patch from 1.0.2 -> 1.0.3).
#   - The release-finalize workflow always bumps to "X.Y.(Z+1)-dev" after a
#     release tag, so most invocations will be from a -dev base.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
PYPROJECT="pyproject.toml"
BUMP_TYPE="${1:-patch}"
CURRENT_BRANCH=$(git branch --show-current)

cd "$ROOT_DIR"

# =============================================================================
# Pre-flight checks
# =============================================================================

if [[ ! -f "$PYPROJECT" ]]; then
    echo "ERROR: $PYPROJECT not found. Run from the repo root." >&2
    exit 1
fi

if [[ "$CURRENT_BRANCH" != "main" ]]; then
    echo "ERROR: Must be on the main branch. Currently on '$CURRENT_BRANCH'." >&2
    exit 1
fi

if [[ -n "$(git status --porcelain)" ]]; then
    echo "ERROR: Working tree is not clean. Commit or stash changes first." >&2
    exit 1
fi

if [[ "$BUMP_TYPE" != "major" && "$BUMP_TYPE" != "minor" && "$BUMP_TYPE" != "patch" ]]; then
    echo "ERROR: Invalid bump type '$BUMP_TYPE'. Use: major, minor, or patch." >&2
    exit 1
fi

if ! command -v gh &>/dev/null; then
    echo "ERROR: GitHub CLI (gh) is required but not installed." >&2
    exit 1
fi

# =============================================================================
# Read current version and compute new version
# =============================================================================

CURRENT_VERSION=$(grep -Po '(?<=^version = ")[^"]+' "$PYPROJECT")
if [[ -z "$CURRENT_VERSION" ]]; then
    echo "ERROR: Could not read version from $PYPROJECT." >&2
    exit 1
fi

CURRENT_TAG=$(git describe --tags --abbrev=0 2>/dev/null || echo "")

BASE_VERSION="${CURRENT_VERSION%%-*}"
IFS='.' read -r V_MAJOR V_MINOR V_PATCH <<< "$BASE_VERSION"

# A "-dev" suffix means "in development for $BASE_VERSION" — the base is the
# target version. Plain "X.Y.Z" with no suffix means the previous release was
# X.Y.Z and we want to bump from there. Treat the two cases differently for
# patch (only); minor and major always increment regardless because skipping
# the in-flight patch is the right behaviour for a major/minor cut.
if [[ "$CURRENT_VERSION" == *-dev ]]; then
  case "$BUMP_TYPE" in
    major) V_MAJOR=$((V_MAJOR + 1)); V_MINOR=0; V_PATCH=0 ;;
    minor) V_MINOR=$((V_MINOR + 1)); V_PATCH=0 ;;
    patch) ;; # no-op: -dev base is already the target patch
  esac
else
  case "$BUMP_TYPE" in
    major) V_MAJOR=$((V_MAJOR + 1)); V_MINOR=0; V_PATCH=0 ;;
    minor) V_MINOR=$((V_MINOR + 1)); V_PATCH=0 ;;
    patch) V_PATCH=$((V_PATCH + 1)) ;;
  esac
fi

NEW_VERSION="${V_MAJOR}.${V_MINOR}.${V_PATCH}"
NEW_TAG="v${NEW_VERSION}"
RELEASE_BRANCH="release/${NEW_VERSION}"

if git rev-parse "$NEW_TAG" >/dev/null 2>&1; then
    echo "ERROR: Tag '$NEW_TAG' already exists." >&2
    exit 1
fi

if git show-ref --verify --quiet "refs/heads/${RELEASE_BRANCH}"; then
    echo "ERROR: Branch '$RELEASE_BRANCH' already exists." >&2
    exit 1
fi

echo "Releasing: $CURRENT_VERSION -> $NEW_VERSION ($BUMP_TYPE)"

# =============================================================================
# Step 1: Create release branch from main
# =============================================================================

echo "Creating release branch: $RELEASE_BRANCH"
git checkout -b "$RELEASE_BRANCH"

# =============================================================================
# Step 2: Bump version, update changelog, rebuild
# =============================================================================

sed -i "s/^version = \"${CURRENT_VERSION}\"/version = \"${NEW_VERSION}\"/" "$PYPROJECT"
python3 "$SCRIPT_DIR/bump_json_versions.py" "$NEW_VERSION"
python3 "$SCRIPT_DIR/update_changelog.py" "$NEW_VERSION" "$(date +%Y-%m-%d)" "$CURRENT_TAG"

echo "Updated version files and CHANGELOG.md"

echo "Running uv lock..."
uv lock

echo "Rebuilding skills and agents..."
make build

git add pyproject.toml \
    .claude-plugin/plugin.json \
    .claude-plugin/marketplace.json \
    .cursor-plugin/cursor.plugin.json \
    CHANGELOG.md \
    uv.lock \
    skills/ \
    agents/

git commit -m "chore: release ${NEW_VERSION}"

# =============================================================================
# Step 3: Push release branch and create PR
# =============================================================================

echo "Pushing release branch..."
git push -u origin "$RELEASE_BRANCH"

echo "Creating pull request..."
RELEASE_NOTES=$(sed -n "/^## \[${NEW_VERSION}\]/,/^## \[/{ /^## \[${NEW_VERSION}\]/d; /^## \[/d; p; }" CHANGELOG.md)

PR_URL=$(gh pr create \
    --base main \
    --head "$RELEASE_BRANCH" \
    --title "Release ${NEW_VERSION}" \
    --body "$(cat <<EOF
## Release ${NEW_VERSION}

${RELEASE_NOTES:-No changelog entries for this release.}

---

**After squash-merging this PR**, the \`release-finalize\` workflow will automatically:
1. Tag the merge commit with \`${NEW_TAG}\`
2. Create a GitHub Release
3. Open a follow-up PR that bumps \`main\` to the next \`-dev\` version
EOF
)")

echo ""
echo "========================================="
echo "  Release PR created: $PR_URL"
echo ""
echo "  Next steps:"
echo "  1. Review the PR"
echo "  2. Squash-merge it into main"
echo "  3. CI will handle tagging, release,"
echo "     and develop sync automatically"
echo "========================================="

# Return to main
git checkout main
