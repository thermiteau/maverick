#!/usr/bin/env bash
set -euo pipefail

# Release script for maverick
# Creates a release on the develop branch, tags it, and merges to main.
#
# Usage: ./scripts/release.sh [major|minor|patch]
# Default: patch

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

PYPROJECT="pyproject.toml"

BUMP_TYPE="${1:-patch}"

CURRENT_BRANCH=$(git branch --show-current)

cd "$ROOT_DIR"

if [[ ! -f "$PYPROJECT" ]]; then
    echo "ERROR: $PYPROJECT not found. Run from the repo root." >&2
    exit 1
fi


# --- Read current values ---

CURRENT_VERSION=$(grep -Po '(?<=^version = ")[^"]+' "$PYPROJECT")
if [[ -z "$CURRENT_VERSION" ]]; then
    echo "ERROR: Could not read version from $PYPROJECT." >&2
    exit 1
fi

CURRENT_TAG=$(git describe --tags --abbrev=0 2>/dev/null || echo "")


# --- Compute new version ---

BASE_VERSION="${CURRENT_VERSION%%-*}"
IFS='.' read -r V_MAJOR V_MINOR V_PATCH <<< "$BASE_VERSION"

case "$BUMP_TYPE" in
  major) V_MAJOR=$((V_MAJOR + 1)); V_MINOR=0; V_PATCH=0 ;;
  minor) V_MINOR=$((V_MINOR + 1)); V_PATCH=0 ;;
  patch) V_PATCH=$((V_PATCH + 1)) ;;
esac

NEW_VERSION="${V_MAJOR}.${V_MINOR}.${V_PATCH}"
NEW_TAG="v${NEW_VERSION}"


# Pre-flight checks
if [[ "$CURRENT_BRANCH" != "develop" ]]; then
    echo "ERROR: Must be on the develop branch. Currently on '$CURRENT_BRANCH'." >&2
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

if ! git merge-base --is-ancestor main develop; then
  echo "Error: 'main' has commits not in 'develop' — merge main into develop first"
  exit 1
fi


if git rev-parse "$NEW_TAG" >/dev/null 2>&1; then
  echo "Error: tag '$NEW_TAG' already exists"
  exit 1
fi

echo "Releasing: $CURRENT_VERSION -> $NEW_VERSION ($BUMP_TYPE)"

# --- Bump version in pyproject.toml ---



bump_version() {
  local ver="$1"
  sed -i "s/^version = \"${CURRENT_VERSION}\"/version = \"${ver}\"/" "$PYPROJECT"
  python3 "$SCRIPT_DIR/bump_json_versions.py" "$ver"
}

TODAY=$(date +%Y-%m-%d)


# --- Step 1: Bump version to release version on develop ---

bump_version "$NEW_VERSION"

# --- Step 2: Update CHANGELOG.md ---

python3 "$SCRIPT_DIR/update_changelog.py" "$NEW_VERSION" "$TODAY" "$CURRENT_TAG"

echo "Updated version files and CHANGELOG.md"

# --- Step 3: Lock, rebuild, and commit release on develop ---

echo "Running uv lock..."
uv lock

echo "Rebuilding skills and agents with new version..."
make build

git add pyproject.toml \
  .claude-plugin/plugin.json \
  .claude-plugin/marketplace.json \
  .cursor-plugin/cursor.plugin.json \
  CHANGELOG.md \
  uv.lock \
  skills/ \
  agents/

git commit -m "$(cat <<EOF
chore: release ${NEW_VERSION}
EOF
)"

git tag -a "$NEW_TAG" -m "Release ${NEW_TAG}"

echo "Release complete"
