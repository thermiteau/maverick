---
title: Maverick Build
scope: Understanding the maverick build process, release workflow, and the rationale behind them
relates-to:
  - maverick-install.md
last-verified: 2026-03-11
---

# Maverick Build

## Templating

Maverick uses Jinja2 templates to generate the skills and agents that make up the Claude Code plugin. While this adds a layer of complexity, it allows frontmatter to be validated and ensures that cross-references between skills and agents are accurate.

### Source structure

Each skill and agent lives under `src/maverick/` with two files:

```
src/maverick/skills/<skill-name>/
  ├── config.py        # SkillConfig — declarative metadata (frontmatter fields, dependencies)
  └── body.md.j2       # Jinja2 template — the skill content

src/maverick/agents/<agent-name>/
  ├── config.py        # AgentConfig — declarative metadata (frontmatter fields, skills list)
  └── body.md.j2       # Jinja2 template — the agent prompt
```

Name constants for all skills and agents are centralised in `src/maverick/names.py` and registered in `ALL_SKILL_NAMES` / `ALL_AGENT_NAMES`.

### Template variables

All templates have access to:

| Variable | Description | Example |
|----------|-------------|---------|
| `{{ SKILLS.<CONSTANT> }}` | Any skill name by its Python constant | `{{ SKILLS.MAV_BP_LOGGING }}` → `mav-bp-logging` |
| `{{ AGENTS.<CONSTANT> }}` | Any agent name by its Python constant | `{{ AGENTS.AGENT_CODE_REVIEWER }}` → `agent-code-reviewer` |
| `{{ ARGUMENTS }}` | User-supplied arguments (skills only) | |
| `{{ DEPENDS_ON }}` | Comma-separated dependency list (skills only) | |

Custom variables can be passed via `extra_context` on `SkillConfig`, `AgentConfig`, or `GlobalConfig`.

### Build output

The registry (`src/maverick/registry.py`) discovers all `config.py` files, renders Jinja2 templates, generates YAML frontmatter from config objects, and writes the output to root-level directories:

- `skills/<name>/SKILL.md` — rendered skills
- `agents/<name>.md` — rendered agents

These root-level directories are **build output** and must never be edited directly.

### Build command

```bash
# Full build (topics + skills + agents)
make build

# Just render skills and agents
make generate
```

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
