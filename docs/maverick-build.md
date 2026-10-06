---
title: Maverick Build
scope: Understanding the maverick build process, release workflow, and the rationale behind them
relates-to:
  - overview.md
last-verified: 2026-07-02
---

# Maverick Build

## Templating

Maverick uses Jinja2 templates to generate the skills and agents that make up the Claude Code plugin. While this adds a layer of complexity, it allows frontmatter to be validated and ensures that cross-references between skills and agents are accurate.

### Source structure

Each skill and agent lives under `src/maverick/` with two files:

```
src/maverick/skills/<skill-name>/
  ├── config.py        # SkillConfig — runtime-neutral metadata (description, invocability, dependencies)
  └── body.md.j2       # Jinja2 template — the skill content

src/maverick/agents/<agent-name>/
  ├── config.py        # AgentConfig — runtime-neutral metadata (description, skills, read_only)
  └── body.md.j2       # Jinja2 template — the agent prompt
```

Configs are runtime-neutral. Options only one runtime understands go in a per-runtime block — for Claude Code, `claude=ClaudeSkillOptions(...)` (e.g. `context="fork"`) or `claude=ClaudeAgentOptions(...)` (e.g. `model`, `color`). Each render target in `src/maverick/targets.py` maps the core fields and its own block onto its frontmatter format; other targets ignore blocks that are not theirs.

Name constants for all skills and agents are centralised in `src/maverick/names.py` and registered in `ALL_SKILL_NAMES` / `ALL_AGENT_NAMES`.

### Template variables

All templates have access to:

| Variable | Description | Example |
|----------|-------------|---------|
| `{{ SKILLS.<CONSTANT> }}` | Any skill name by its Python constant | `{{ SKILLS.MAV_BP_OPERABILITY }}` → `mav-bp-operability` |
| `{{ AGENTS.<CONSTANT> }}` | Any agent name by its Python constant | `{{ AGENTS.AGENT_CODE_REVIEWER }}` → `agent-code-reviewer` |
| `{{ ARGUMENTS }}` | User-supplied arguments (skills only) | |
| `{{ RUNTIME.<KEY> }}` | Runtime-specific wording from the render target (`src/maverick/targets.py`) | `{{ RUNTIME.NAME }}` → `Claude Code` |
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

# Render one runtime target's complete plugin (skills, agents, hooks) into a directory
cd src && python -m maverick.registry --target claude --out /tmp/maverick-claude
```

## Releasing

Releases are created using `scripts/release.sh`. The script bumps the version across all manifest files, updates the changelog, and commits on a release branch — keeping the process repeatable and consistent. Tagging happens in CI (`release-finalize.yml`) after the release PR is merged, not in the script.

### Version locations

The version string appears in four files that must stay in sync:

| File | Format |
|------|--------|
| `pyproject.toml` | `version = "X.Y.Z"` |
| `.claude-plugin/plugin.json` | `"version": "X.Y.Z"` |
| `.claude-plugin/marketplace.json` | top-level `version` only — the plugin entry has no `version`; the plugin's own `plugin.json` carries it |
| `.cursor-plugin/cursor.plugin.json` | `"version": "X.Y.Z"` |

`uv.lock` also contains the version but is regenerated automatically by `uv lock` during the release.

### Usage

The script takes a **bump type** — `major`, `minor`, or `patch` (default `patch`). It computes the next version from the current `-dev` version; it does **not** accept an explicit version number.

```bash
# Create a patch release (default)
./scripts/release.sh patch

# Or a minor / major release
./scripts/release.sh minor
./scripts/release.sh major

# Equivalent Make targets
make release          # patch
make release-minor    # minor
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

After the release PR squash-merges into `main`, three jobs run in order:

1. **`finalize`** — tags the merge commit `vX.Y.Z`, creates a GitHub Release with notes extracted from `CHANGELOG.md`, and opens a follow-up PR (`chore/begin-X.Y.(Z+1)-dev-cycle`) that bumps `main` back to the next `-dev` version
2. **`publish-pypi`** — builds the CLI from the tag and publishes it to PyPI as `maverick-harness` (trusted publishing, `pypi` environment)
3. **`publish-plugin`** — renders the Claude Code plugin (`python -m maverick.registry --target claude --out …`), commits it to [thermiteau/maverick-claude](https://github.com/thermiteau/maverick-claude) as `Release vX.Y.Z` with a matching tag, then fast-forwards `stable` to the release tag

The order is deliberate. A released plugin installs the CLI release matching its own version from PyPI, so the plugin only becomes visible to users — through `maverick-claude` and through the marketplace entry on `stable` — after its CLI is published. If PyPI publishing fails, neither moves.

### Where the plugin is installed from

The `thermite` marketplace (`.claude-plugin/marketplace.json`, read by users from `stable`) lists the `maverick` plugin with a `github` source pointing at `thermiteau/maverick-claude`. That repository holds only the rendered plugin, and its default branch always holds the latest release; it is never edited by hand. Users get a new copy when the plugin's `plugin.json` version changes.

### The `stable` branch

`stable` is the branch end users install from — a bare `git clone git@github.com:thermiteau/maverick.git` resolves to it because `stable` is GitHub's default branch. It always points at the most recent release tag. Between releases `main` moves forward with feature PRs, but `stable` stays frozen on the last tagged commit, so consumers who pull updates only see new code once an actual release happens.

No human pushes to `stable`. The only writer is the `Fast-forward stable branch to the new release` step in `release-finalize.yml`, which runs after tagging.
