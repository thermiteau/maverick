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

# Pre-flight checks
cd "$ROOT_DIR"

BRANCH=$(git rev-parse --abbrev-ref HEAD)
if [[ "$BRANCH" != "main" ]]; then
  echo "Error: must be on 'main' branch (currently on '$BRANCH')"
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

TODAY=$(date +%Y-%m-%d)

echo "Releasing $VERSION ($TAG) on $TODAY"

if $DRY_RUN; then
  echo ""
  echo "[dry-run] Would update version to $VERSION in:"
  echo "  - pyproject.toml"
  echo "  - .claude-plugin/plugin.json"
  echo "  - .claude-plugin/marketplace.json (top-level + plugins[0])"
  echo "  - .cursor-plugin/cursor.plugin.json"
  echo "[dry-run] Would update CHANGELOG.md: add [${VERSION}] - ${TODAY} section"
  echo "[dry-run] Would run: uv lock"
  echo "[dry-run] Would commit: chore: release ${VERSION}"
  echo "[dry-run] Would create annotated tag: ${TAG}"
  exit 0
fi

# Update pyproject.toml
sed -i "s/^version = \".*\"/version = \"$VERSION\"/" pyproject.toml

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
" "$VERSION"

# Update CHANGELOG.md
# Find the previous tag for comparison links
PREV_TAG=$(git describe --tags --abbrev=0 2>/dev/null || echo "")

python3 -c '
import sys, re

version = sys.argv[1]
today = sys.argv[2]
prev_tag = sys.argv[3]
tag = "v" + version

with open("CHANGELOG.md") as f:
    content = f.read()

# Insert new version section after ## [Unreleased]
new_heading = "## [Unreleased]\n\n## [{v}] - {d}".format(v=version, d=today)
content = content.replace("## [Unreleased]", new_heading, 1)

# Update comparison links at the bottom
# Change [Unreleased] link to compare from new tag
content = re.sub(
    r"\[Unreleased\]: (https://github\.com/[^/]+/[^/]+)/compare/.*\.\.\.HEAD",
    r"[Unreleased]: \g<1>/compare/" + tag + "...HEAD",
    content
)

# Add new version link before existing version links
if prev_tag:
    unreleased_link_pattern = r"(\[Unreleased\]: https://github\.com/[^\n]+\n)"
    repo_match = re.search(r"\[Unreleased\]: (https://github\.com/[^/]+/[^/]+)/", content)
    if repo_match:
        repo_url = repo_match.group(1)
        new_link = "[" + version + "]: " + repo_url + "/compare/" + prev_tag + "..." + tag + "\n"
        content = re.sub(unreleased_link_pattern, r"\g<1>" + new_link, content)

with open("CHANGELOG.md", "w") as f:
    f.write(content)
' "$VERSION" "$TODAY" "$PREV_TAG"

echo "Updated version files and CHANGELOG.md"

# Sync lockfile
echo "Running uv lock..."
uv lock

# Commit and tag
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

git tag -a "$TAG" -m "Release $VERSION"

echo ""
echo "Release $TAG created locally."
echo "To publish:"
echo "  git push origin main --tags"
echo "  gh release create $TAG --generate-notes"
