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

The release script follows a trunk-based flow. `main` carries the current `-dev` version between releases. The script cuts a short-lived `release/<version>` branch from `main`, bumps the version, and opens a PR back to `main`. After the PR squash-merges, `release-finalize.yml` takes over: tag, GitHub Release, and a follow-up PR that bumps `main` to the next `-dev` version.

**Local phase** (`scripts/release.sh`):

1. **Pre-flight checks** — validates the current branch is `main`, the working tree is clean, the computed version has not already been tagged, and the release branch does not already exist
2. Creates `release/<version>` from `main`
3. Bumps the version to `X.Y.Z` in `pyproject.toml`, `.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json`, and `.cursor-plugin/cursor.plugin.json`
4. Updates `CHANGELOG.md` — adds a dated version section below `[Unreleased]` and updates comparison links
5. Runs `uv lock` and `make build` to refresh the lockfile and regenerated output
6. Commits on `release/<version>`: `chore: release X.Y.Z`
7. Pushes the release branch and creates a PR targeting `main` with the release notes

**CI phase** (`.github/workflows/release-finalize.yml`):

After the release PR squash-merges into `main`:

1. Tags the merge commit `vX.Y.Z`
2. Creates a GitHub Release with notes extracted from `CHANGELOG.md`
3. Fast-forwards the `stable` branch to the new tag commit (this is what end users clone)
4. Opens a follow-up PR (`chore/begin-X.Y.(Z+1)-dev-cycle`) that bumps `main` back to the next `-dev` version

### The `stable` branch

`stable` is the branch end users install from — a bare `git clone git@github.com:thermiteau/maverick.git` resolves to it because `stable` is GitHub's default branch. It always points at the most recent release tag. Between releases `main` moves forward with feature PRs, but `stable` stays frozen on the last tagged commit, so consumers who pull updates only see new code once an actual release happens.

No human pushes to `stable`. The only writer is the `Fast-forward stable branch to the new release` step in `release-finalize.yml`, which runs after tagging.
