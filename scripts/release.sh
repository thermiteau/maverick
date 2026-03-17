#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

DRY_RUN=false
VERSION=""

usage() {
  echo "Usage: $0 [--dry-run] <version>"
  echo "  version   Semver version (e.g. 0.2.0 or 0.2.0-alpha)"
  echo "  --dry-run Preview changes without modifying anything"
  exit 1
}

# Parse arguments
while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run) DRY_RUN=true; shift ;;
    -h|--help) usage ;;
    -*) echo "Unknown option: $1"; usage ;;
    *) VERSION="$1"; shift ;;
  esac
done

[[ -z "$VERSION" ]] && usage

# Validate semver format
if ! [[ "$VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+(-[a-zA-Z0-9.]+)?$ ]]; then
  echo "Error: '$VERSION' is not a valid semver version"
  exit 1
fi

TAG="v$VERSION"

compute_next_dev_version() {
  local ver="$1"
  local major minor
  major=$(echo "$ver" | cut -d. -f1)
  minor=$(echo "$ver" | cut -d. -f2)
  echo "${major}.$((minor + 1)).0-dev"
}

bump_version() {
  local ver="$1"

  # Update pyproject.toml
  sed -i "s/^version = \".*\"/version = \"$ver\"/" pyproject.toml

  # Update JSON files using Python (safer than sed for JSON)
  python3 -c "
import json, sys

def update_json(path, updates):
    with open(path) as f:
        data = json.load(f)
    for keys, value in updates:
        obj = data
        for k in keys[:-1]:
            obj = obj[k]
        obj[keys[-1]] = value
    with open(path, 'w') as f:
        json.dump(data, f, indent=2)
        f.write('\n')

version = sys.argv[1]

update_json('.claude-plugin/plugin.json', [
    (['version'], version),
])

update_json('.claude-plugin/marketplace.json', [
    (['version'], version),
    (['plugins', 0, 'version'], version),
])

update_json('.cursor-plugin/cursor.plugin.json', [
    (['version'], version),
])
" "$ver"
}

# Pre-flight checks
cd "$ROOT_DIR"

BRANCH=$(git rev-parse --abbrev-ref HEAD)
if [[ "$BRANCH" != "develop" ]]; then
  echo "Error: must be on 'develop' branch (currently on '$BRANCH')"
  exit 1
fi

if ! git diff --quiet || ! git diff --cached --quiet; then
  echo "Error: working tree is not clean — commit or stash changes first"
  exit 1
fi

if git rev-parse "$TAG" >/dev/null 2>&1; then
  echo "Error: tag '$TAG' already exists"
  exit 1
fi

if ! git merge-base --is-ancestor main develop; then
  echo "Error: 'main' has commits not in 'develop' — merge main into develop first"
  exit 1
fi

TODAY=$(date +%Y-%m-%d)
NEXT_DEV_VERSION=$(compute_next_dev_version "$VERSION")

echo "Releasing $VERSION ($TAG) on $TODAY"
echo "Next dev version: $NEXT_DEV_VERSION"

if $DRY_RUN; then
  echo ""
  echo "[dry-run] Would perform the following steps:"
  echo ""
  echo "  1. Bump version to $VERSION in:"
  echo "     - pyproject.toml"
  echo "     - .claude-plugin/plugin.json"
  echo "     - .claude-plugin/marketplace.json (top-level + plugins[0])"
  echo "     - .cursor-plugin/cursor.plugin.json"
  echo "  2. Update CHANGELOG.md: add [${VERSION}] - ${TODAY} section"
  echo "  3. Run: uv lock"
  echo "  4. Commit on develop: chore: release ${VERSION}"
  echo "  5. Checkout main, merge --no-ff develop"
  echo "  6. Create annotated tag: ${TAG}"
  echo "  7. Checkout develop, bump version to ${NEXT_DEV_VERSION}"
  echo "  8. Run: uv lock"
  echo "  9. Commit on develop: chore: begin ${NEXT_DEV_VERSION} cycle"
  echo ""
  echo "After running without --dry-run:"
  echo "  git push origin main develop --tags"
  echo "  gh release create $TAG --generate-notes"
  exit 0
fi

# --- Step 1: Bump version to release version on develop ---

bump_version "$VERSION"

# --- Step 2: Update CHANGELOG.md ---

PREV_TAG=$(git describe --tags --abbrev=0 2>/dev/null || echo "")

python3 -c "
import sys, re

version = sys.argv[1]
today = sys.argv[2]
prev_tag = sys.argv[3]
tag = 'v' + version

with open('CHANGELOG.md') as f:
    content = f.read()

# Insert new version section after ## [Unreleased]
content = content.replace(
    '## [Unreleased]',
    '## [Unreleased]\n\n## [\${v}] - \${d}'.replace('\${v}', version).replace('\${d}', today),
    1
)

# Update comparison links at the bottom
# Change [Unreleased] link to compare from new tag
content = re.sub(
    r'\[Unreleased\]: (https://github\.com/[^/]+/[^/]+)/compare/.*\.\.\.HEAD',
    r'[Unreleased]: \g<1>/compare/' + tag + '...HEAD',
    content
)

# Add new version link before existing version links
if prev_tag:
    # Insert new version comparison link
    unreleased_link_pattern = r'(\[Unreleased\]: https://github\.com/[^\n]+\n)'
    repo_match = re.search(r'\[Unreleased\]: (https://github\.com/[^/]+/[^/]+)/', content)
    if repo_match:
        repo_url = repo_match.group(1)
        new_link = '[' + version + ']: ' + repo_url + '/compare/' + prev_tag + '...' + tag + '\n'
        content = re.sub(unreleased_link_pattern, r'\g<1>' + new_link, content)

with open('CHANGELOG.md', 'w') as f:
    f.write(content)
" "$VERSION" "$TODAY" "$PREV_TAG"

echo "Updated version files and CHANGELOG.md"

# --- Step 3: Lock and commit release on develop ---

echo "Running uv lock..."
uv lock

git add pyproject.toml \
  .claude-plugin/plugin.json \
  .claude-plugin/marketplace.json \
  .cursor-plugin/cursor.plugin.json \
  CHANGELOG.md \
  uv.lock

git commit -m "$(cat <<EOF
chore: release ${VERSION}
EOF
)"

# --- Step 4: Merge to main and tag ---

git checkout main
git merge --no-ff develop -m "Merge develop for release ${VERSION}"
git tag -a "$TAG" -m "Release $VERSION"

echo "Tagged $TAG on main"

# --- Step 5: Return to develop and bump to next dev version ---

git checkout develop

bump_version "$NEXT_DEV_VERSION"

echo "Running uv lock..."
uv lock

git add pyproject.toml \
  .claude-plugin/plugin.json \
  .claude-plugin/marketplace.json \
  .cursor-plugin/cursor.plugin.json \
  uv.lock

git commit -m "$(cat <<EOF
chore: begin ${NEXT_DEV_VERSION} cycle
EOF
)"

echo ""
echo "Release $TAG created locally."
echo "To publish:"
echo "  git push origin main develop --tags"
echo "  gh release create $TAG --generate-notes"
