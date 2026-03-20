---
title: Maverick Build
scope: Understanding the maverick build process, release workflow, and the rationale behind them
relates-to:
  - maverick-install.md
last-verified: 2026-03-20
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
- `infra/maverick-vpc.template.json` — CloudFormation VPC template
- `infra/maverick-infra.template.json` — CloudFormation infrastructure template

The `infra/` templates are standalone CloudFormation files that users can upload directly to the AWS Console for manual deployment. They are generated from the same template builders used by the CLI (`_build_vpc_template` and `_build_infra_template` in `src/maverick/infra.py`). The Lambda handler source and cloud-init user data are read from `src/maverick/` and embedded inline during the build.

All root-level output directories (`skills/`, `agents/`, `infra/`) are **build output** and must never be edited directly.

### Build command

```bash
# Full build (topics + skills + agents + CloudFormation templates)
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

The release script follows a develop-first flow: the release is prepared on `develop`, merged to `main`, tagged, and then `develop` is bumped to the next dev version so it always stays ahead of `main`.

1. **Pre-flight checks** — validates the version is valid semver, the branch is `develop`, the working tree is clean, the tag does not already exist, and `main` is an ancestor of `develop`
2. Bumps the version to `X.Y.Z` in all four manifest files
3. Updates `CHANGELOG.md` — adds a dated version section below `[Unreleased]` and updates comparison links
4. Runs `uv lock` to sync the lockfile
5. Commits on `develop`: `chore: release X.Y.Z`
6. Checks out `main` and merges `develop` with `--no-ff`
7. Creates an annotated git tag `vX.Y.Z` on `main`
8. Checks out `develop` and bumps the version to `X.(Y+1).0-dev` in all four manifest files
9. Runs `uv lock` and commits: `chore: begin X.(Y+1).0-dev cycle`

After running the script, push both branches and the tag, then create a GitHub release:

```bash
git push origin main develop --tags
gh release create vX.Y.Z --generate-notes
```
