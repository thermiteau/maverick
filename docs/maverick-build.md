---
title: Maverick Build
scope: Understanding the maverick build process, release workflow, and the rationale behind them
relates-to:
  - maverick-install.md
last-verified: 2026-03-06
---

# Maverick Build

## Templating

The maverick plaugin uses tempaltes to create the skills and agents that make up the Claude Code plaugin. While this adds a layer of complexity, it allows the frontmatter to be validated and ensures that references to other sklills can be validated.

The build process uses the template under a given skills folder `SKILL.md.template` and the config file `config.py` that holds all the variables.

This way we can be sure that cross references are accurate and that the Claude skill fronmatter schema is adhered to

## Releasing

Releases are created using `scripts/release.sh`. The script bumps the version across all manifest files, updates the changelog, commits, and tags — keeping the process repeatable and consistent.

### Version locations

The version string appears in four files that must stay in sync:

| File | Format |
|------|--------|
| `pyproject.toml` | `version = "X.Y.Z"` |
| `.claude-plugin/plugin.json` | `"version": "X.Y.Z"` |
| `.claude-plugin/marketplace.json` | top-level `version` and `plugins[0].version` |
| `.cursor-plugin/cursor.plugin.json` | `"version": "X.Y.Z"` |

`uv.lock` also contains the version but is regenerated automatically by `uv lock` during the release.

### Usage

```bash
# Preview what the release will do (no files modified)
./scripts/release.sh --dry-run 0.2.0

# Create a release
./scripts/release.sh 0.2.0

# Or via Make
make release VERSION=0.2.0
```

### What the script does

1. Validates the version is valid semver, the branch is `main`, the working tree is clean, and the tag does not already exist
2. Updates the version in all four manifest files
3. Updates `CHANGELOG.md` — adds a dated version section below `[Unreleased]` and updates comparison links
4. Runs `uv lock` to sync the lockfile
5. Commits all changes: `chore: release X.Y.Z`
6. Creates an annotated git tag: `vX.Y.Z`

After running the script, push and create a GitHub release:

```bash
git push origin main --tags
gh release create vX.Y.Z --generate-notes
```
