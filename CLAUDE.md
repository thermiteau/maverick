# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Maverick is a Claude Code plugin and Python CLI that enables autonomous AI-driven software development with enforced quality, security, and operational best practices. It has three components:

1. **Claude Code Plugin** — markdown skills (in `skills/`) and agents (in `agents/`) that define workflows, best practices, and execution patterns
2. **Python CLI** (`src/maverick/`, aliased from `cli/`) — project initialization, plugin management, and AWS infrastructure provisioning
3. **Documentation** (`docs/`) — architecture, philosophy, and enforcement mechanisms

## Build & Run Commands

```bash
# Install dependencies
uv sync

# Run CLI from source
uv run maverick --help
uv run maverick init --dry-run

# Install system-wide
uv tool install .

# Install in dev mode
uv tool install -e .

# Load plugin from local source for testing
claude --plugin-dir ./maverick-plugin

# Run integration tests
bash tests/integration/test_cli.sh
bash tests/integration/test_real_repos.sh

# Create a release (two-phase: local prep + CI finalize)
# Phase 1 — run locally from the main branch:
./scripts/release.sh patch   # or: minor, major
# This creates a release/<version> branch from main, bumps version, and opens a PR.
# Phase 2 — automatic after squash-merging the PR:
# CI tags main, creates GitHub Release, then opens a follow-up PR
# that bumps main to the next -dev version.
```

## Architecture

### Skills (`skills/<name>/SKILL.md`)

Markdown files with YAML frontmatter that define machine-readable workflows and best practices. Two categories:

- **Best-practice skills** (non-invocable): Universal standards for logging, alerting, linting, testing, CI/CD, git workflow, scope boundaries
- **Workflow skills** (user-invocable): Orchestrate multi-step processes — `do-issue-solo` (autonomous from GitHub issue), `do-issue-guided` (interactive with checkpoints from GitHub issue), `do-task-solo` (autonomous from user-described task, no GitHub issue), `upskill` (generate project-specific skills), `maverick-alignment` (codebase audit)

Skills compose via a `Depends on:` declaration. The three primary entry points are `do-issue-solo`, `do-issue-guided`, and `do-task-solo`, which chain through: understand → design → create tasks → branch → implement → review → push → PR. The `create-tasks` skill decomposes a solution design into discrete tasks — posted as a checklist comment for < 5 tasks, or as GitHub sub-issues for >= 5 tasks.

### Agents (`agents/*.md`)

Autonomous workers dispatched as subagents: `code-reviewer.md` (two-stage: spec compliance then code quality), `tech-docs-writer.md`.

### CLI (`cli/`)

Entry point: `cli/cli.py` → `maverick.cli:main`. Commands: `init`, `plugin`, `clean`, `build-ami`, `instance`, `infra`, `worker`. Uses lazy imports per command. Config stored in `.maverick/config.json` (project) and `~/.maverick/config.json` (user).

The `init` command auto-detects tech stacks by scanning for `package.json`, `pyproject.toml`, `build.gradle.kts`, `Dockerfile`, `.github/workflows/`, etc.

### Enforcement Chain

Every practice area follows a 6-layer pattern: best-practice skill → project skill → local verification → CI pipeline → agent review → human review.

## Critical: Source Code vs Build Output

The root-level `/skills/`, `/agents/`, and `/hooks/` directories are **build output** — they are generated from source and must NEVER be edited directly. All skill, agent, and hook source files live under `src/maverick/`.

When creating or editing skills, agents, or hooks, always work in `src/maverick/`. Never create or modify files in the root `/skills/`, `/agents/`, or `/hooks/` directories.

### Creating or Editing Skills

Each skill lives in `src/maverick/skills/<name>/` and requires **two files**:

1. **`config.py`** — Declarative configuration using `SkillConfig` from `maverick.models`. Name constants come from `maverick.names`.

   ```python
   from maverick.models import SkillConfig
   from maverick.names import MY_SKILL, SOME_DEPENDENCY

   CONFIG = SkillConfig(
       name=MY_SKILL,
       description="What this skill does.",
       argument_hint="optional hint for arguments",
       user_invocable=True,
       disable_model_invocation=False,
       depends_on=[SOME_DEPENDENCY],
   )
   ```

2. **`body.md.j2`** — A Jinja2 template file containing the skill content as markdown (no YAML frontmatter — that is generated from `config.py`). Uses Jinja2 syntax (`{{ variable }}`). The following variables are available:
   - `{{ ARGUMENTS }}` — user-supplied arguments at runtime
   - `{{ DEPENDS_ON }}` — comma-separated list of dependency names from `config.py`
   - `{{ SKILLS.<CONSTANT> }}` — any skill name, where `<CONSTANT>` is the Python constant from `names.py` (e.g., `{{ SKILLS.MAV_BP_LOGGING }}` → `mav-bp-logging`)
   - `{{ AGENTS.<CONSTANT> }}` — any agent name (e.g., `{{ AGENTS.AGENT_CODE_REVIEWER }}` → `agent-code-reviewer`)
   - Any key from `extra_context` on the `SkillConfig` or `GlobalConfig`

When adding a new skill, also add a name constant to `src/maverick/names.py` and register it in `ALL_SKILL_NAMES`.

### Creating or Editing Agents

Each agent lives in `src/maverick/agents/<name>/` and requires **two files**:

1. **`config.py`** — Declarative configuration using `AgentConfig` from `maverick.models`. Name constants come from `maverick.names`.

   ```python
   from maverick.models import AgentConfig
   from maverick.names import AGENT_MY_AGENT, SOME_SKILL

   CONFIG = AgentConfig(
       name=AGENT_MY_AGENT,
       description="What this agent does.",
       skills=[SOME_SKILL],
   )
   ```

2. **`body.md.j2`** — A Jinja2 template file containing the agent prompt as markdown (no frontmatter). Uses Jinja2 syntax (`{{ variable }}`). The following variables are available:
   - `{{ SKILLS.<CONSTANT> }}` — any skill name (e.g., `{{ SKILLS.MAV_BP_LOGGING }}` → `mav-bp-logging`)
   - `{{ AGENTS.<CONSTANT> }}` — any agent name (e.g., `{{ AGENTS.AGENT_CODE_REVIEWER }}` → `agent-code-reviewer`)
   - Any key from `extra_context` on the `AgentConfig`

When adding a new agent, also add a name constant (prefixed `AGENT_`) to `src/maverick/names.py` and register it in `ALL_AGENT_NAMES`.

### Building Skills & Agents

After editing source files, regenerate the build output:

```bash
# Render all skills and agents to root-level /skills/ and /agents/
make build
# or directly:
cd src && python -m maverick.registry
```

The registry (`src/maverick/registry.py`) discovers all `config.py` files, renders templates, generates YAML frontmatter, and writes output to the root-level directories.

## Key Conventions

- **Git workflow**: Trunk-based with a stable tracking branch.
  - `main` is where development happens: it carries the current `-dev` version between releases, and is tagged `vX.Y.Z` at each release. No direct commits or pushes to `main` — all changes land via squash-merged PRs.
  - `stable` is the branch end users install from (it is GitHub's default branch, so a bare `git clone` resolves to it). It is automatically fast-forwarded to the latest release tag by `release-finalize.yml` and never moves during `-dev` cycles. No human ever pushes to `stable` — it is CI-managed.
  - Feature branches are short-lived, branch from `main`, and PR back to `main`: `<type>/<issue>-<desc>` (e.g., `feat/42-add-export`). Release branches (`release/<version>`) are short-lived and exist only long enough to cut a release.
  - Conventional Commits with issue refs: `feat: add export button (#42)`.
  - When creating PRs programmatically (e.g., via `gh pr create`), always pass `--base main` explicitly, because the repository's default branch is `stable`.
- **Scope boundaries** (`skills/mav-scope-boundaries/`): Four hard limits — no infrastructure changes without explicit issue authorization, no auth/permissions changes without human review, no destructive git ops without session consent, never touch production systems.
- **Python**: 3.10+, `uv` package manager, `boto3` for AWS, `argparse` CLI framework.
- **Skills format**: Source is `config.py` (frontmatter fields) + `body.md.j2` (Jinja2 template). Both skills and agents use `{{ SKILLS.CONSTANT }}` / `{{ AGENTS.CONSTANT }}` to reference other skills/agents. Build output is generated YAML frontmatter + rendered markdown.
