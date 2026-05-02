# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [2.0.2] - 2026-05-01

## [2.0.1] - 2026-04-29

## [2.0.0] - 2026-04-28

## [1.0.3] - 2026-04-28

## [1.0.2] - 2026-04-27

Tooling release. Fixes two bugs in the release pipeline that surfaced during the 1.0.0 and 1.0.1 cuts.

### Fixed

- **`release-finalize.yml` fast-forwards `stable` via the REST API** instead of `git push`. The previous `git push origin "refs/tags/${TAG}:refs/heads/stable"` step was rejected on every release run with `[remote rejected] (failed)` even when named branch protection and rulesets were disabled. The same fast-forward update via `gh api -X PATCH .../git/refs/heads/stable` succeeds with identical auth, so the workflow now uses the REST endpoint. The fast-forward safety guarantee is preserved (REST `PATCH` on a ref returns 422 on a non-fast-forward unless `force: true` is passed, which we don't). No new dependency — `gh` is preinstalled on GitHub-hosted runners.
- **`release.sh patch` correctly handles `-dev` suffix.** Running `./scripts/release.sh patch` from a `-dev` version (e.g., `1.0.2-dev`) was producing the next-next patch (`1.0.3`) instead of the in-development target (`1.0.2`). The script now detects the `-dev` suffix and treats the base as the target — patch is a no-op when the current version is `-dev`, since the base IS the target. Minor and major still increment in both cases, so `minor` from a `-dev` cycle correctly skips the in-flight patch (e.g. `1.0.2-dev` → `1.1.0`). Header docstring expanded to spell out the convention.

## [1.0.1] - 2026-04-27

Housekeeping release.

### Removed

- `temp/` scratch directory containing the four planning notes that informed the 1.0.0 workflow overhaul (`workflow.md`, `plan.md`, `retro.md`, `outstanding.md`). Their content all shipped as skills and docs in 1.0.0; the directory was leftover noise.

## [1.0.0] - 2026-04-27

First major release. The workflow shape changes substantially: every Maverick action now passes through a unified preflight gate, two mandatory pre-push reviews (docs and cybersecurity), and a tightened code-review contract. Project state — including which Maverick milestones a project has reached — is tracked durably in `.maverick/config.json` and committed to git.

### Added

- **`do-cybersecurity-review` skill** — full-audit mode at adoption time produces `docs/security-audit.md`; update mode runs as a mandatory pre-push gate against the diff plus its impact set, returning `PASS` / `FINDINGS` / `BLOCKING` verdicts. Eight audit categories covering secrets, dependencies, auth, input validation, transport/headers, data at rest, logging/monitoring, and container/IaC.
- **`mav-bp-remote-code-review` skill** with a shipped reference workflow YAML — codifies the contract for a CI-side code review on every PR via Anthropic's `claude-code-action` (or any equivalent). Marker comment `# maverick:code-review` decouples the audit from action specifics.
- **`maverick preflight <skill>` CLI** — single unified gate every action skill calls as its first mandatory step. Checks integration flags, PATH tools (`gh`, `git`, `uv`), and named runtime checks (`bot_configured`, `worktrees_enabled`). Exit-code-driven; no skip path.
- **`maverick integration get/set` CLI** + the `integration` block in `.maverick/config.json` — durably tracks per-project milestones (`init`, `alignment`, `upskill`, `tech_docs_scaffolded`, `code_review_workflow`, `cybersecurity_reviewed`).
- **CI workflow (`ci.yml`)** with parallel jobs: test, lint, typecheck, build-drift, build-determinism, install-smoke. Runs on every push and PR.
- **Plugin-integrity tests** — verify skill `depends_on` cross-references, agent `skills` references, plugin-manifest path resolution, and `hooks.json` event-name validity.
- **`SkillConfig.assets`** mechanism — declarative non-template files shipped alongside skills, used by `mav-bp-remote-code-review` for its reference YAML.
- **SessionStart hook** — auto-installs the CLI on first session if missing (Claude Code has no `PluginInstall` lifecycle event; this is the closest fit).
- **`docs/do-issue-workflow.md`** — full mermaid + phase walkthrough of the GitHub-issue-driven autonomous workflow.
- Mandatory pre-push **documentation review** (always runs, no skip path) via `agent-tech-docs-writer` update mode.
- `do-init` Step 6 dispatches `do-cybersecurity-review` after `do-upskill`, producing an audit at adoption time.

### Changed

- **`do-init` rewritten** — now installs the CLI first (dispatching `do-install` if `maverick` is not on PATH), runs `uv run maverick init` to produce `.maverick/config.json` with the integration block, and orchestrates `do-docs`, `do-upskill`, and `do-cybersecurity-review` in sequence.
- **`do-install` rewritten as a Python module** (`maverick.install_cli`) — replaces the broken bash `install.sh` reference. Type-checked, lint-checked, unit-tested. Verifies `uv` and `gh` are present, runs `uv tool install --force`, idempotently updates `~/.claude/settings.json` permissions.
- **`agent-code-reviewer` scope tightened** to a pure quality gate: correctness, test coverage, spec compliance, scope discipline, maintainability, consistency. **Security is explicitly out of scope** — handled by the pre-push `do-cybersecurity-review` gate. `mav-bp-code-review` and `docs/code-review.md` aligned with the new boundary.
- `do-issue-solo` and `do-issue-guided` gain new mandatory pre-push phases (Documentation Review and Pre-push Cybersecurity Review). Existing phases renumbered.
- `docs/security-review.md` rewritten to ground in `do-cybersecurity-review` and the `mav-bp-application-security` standard, removing duplicated standards content.
- `docs/overview.md`, `docs/architecture.md`, `docs/code-review.md`, `docs/claude-code-error-handling-and-recovery.md` updated to reflect the new gates and removed components.

### Removed (BREAKING)

- **`do-task-solo` skill** — the local-file workflow is removed. All Maverick development now originates from a GitHub issue. The local-file path bypassed multi-instance coordination, claim/lease, DAG persistence, and the auditable comment trail; maintaining two paths fragmented the workflow and created silent escape hatches around the binary review gate. Migration: switch to `/maverick:do-issue-solo` against a GitHub issue.
- **`agent-task-planner` agent** — used only by `do-task-solo`, removed alongside it.

### Fixed

- `topics.json` being silently wiped by `make build` (`generate` ran after `generate-topics` and `_clean_skills_output` removed the directory). Makefile build order corrected; `topics.json` is now a tracked artefact.
- `do-install` skill referenced an `install.sh` that had been deleted in commit `c2a3344`, leaving the skill broken for every user since.
- `hooks.json` registered an invalid `PostPush` event that Claude Code silently rejected. Replaced with `SessionStart`. Plugin-integrity test now codifies the valid event-name set.
- `.cursor-plugin/cursor.plugin.json` referenced `./hooks/hooks.json` after the file was temporarily deleted; reference restored alongside the rebuilt hook.
- `do-init` previously wrote `.maverick/settings.json` by hand and never invoked the CLI, so the integration block was never created. Now uses `maverick init` and only writes settings.json if it doesn't already exist (was overwriting before).
- `gh` CLI presence is now checked at install time with platform-specific install instructions (was failing at runtime with cryptic errors).

## [0.5.7] - 2026-04-22

### Added

- New `do-recommend` skill — scans a project for missing best-practice areas (currently linting and unit testing) and writes 1–3 ranked technology recommendations per gap to `docs/maverick/recommendations/<topic>.md`. Supports optional single-topic invocation.
- New `do-adopt` skill — action counterpart to `do-recommend`. Installs and configures the top-recommended tool per gap (packages, config files, ignore patterns, run scripts), verifies the setup, and commits. Reuses an existing recommendation file when present.
- Full implementation of `maverick init` — auto-detects tech stacks (Node, Python, Go, Rust, JVM, Docker, GitHub Actions, GitLab CI, Azure Pipelines, Terraform, AWS CDK) via marker-file scanning, writes `.maverick/config.json`, and supports `--override`, `--add`, `--remove`, `--dry-run`, and `--platform` flags.
- Full implementation of `maverick plugin install` / `uninstall` — manages Maverick's entry in the `pluginDirs` list of `~/.claude/settings.json`, with `--dev` for the local plugin path and `--clean` to also remove `.maverick/` on uninstall.
- Full implementation of `maverick clean` — removes the project `.maverick/` directory with `--dry-run` support.

### Changed

- Renamed `do-task-solo` artifact from `design.md` to `solution-design.md` for consistency with `mav-create-solution-design` terminology. All phase references and the `agent-task-planner` prompt updated to match.
- `do-upskill` generated-skill frontmatter now includes a required `name: <topic-name>` field across the detected, recommended, and stub templates.

## [0.5.5] - 2026-03-19

## [0.5.3] - 2026-03-19

## [0.5.1] - 2026-03-19

### Added

- Python unit test suite (160 tests) covering models, names, config, registry, CLI, lambda handler, and session review modules (parser, analyzers, reporter, skills)
- GitHub Actions workflow (`unit-tests.yml`) — runs unit tests on push to `develop`
- `pytest>=8.0` as an optional `test` dependency in `pyproject.toml`

## [0.4.0] - 2026-03-18

### Added

- New `create-tasks` skill — decomposes a solution design into discrete, independently implementable tasks. For fewer than 5 tasks, posts a checklist comment on the issue. For 5 or more, creates GitHub sub-issues with dependency ordering. Replaces the `create-implementation-plan` and `task-breakdown` skills with a single, simpler concept
- New `do-issue-guided` workflow skill — interactive counterpart to `do-issue-solo`. Works through the same phases (understand → design → create tasks → branch → implement → review → push → PR) but pauses at four checkpoints (design review, tasks review, review results, completion) for user confirmation. Proceeds autonomously between checkpoints.
- New `do-task-solo` workflow skill — autonomous end-to-end task execution without GitHub issues. The user describes what they want interactively, and Claude formalises it as a structured task document, then designs, creates tasks, and implements them. All artifacts (task description, design, tasks, completion) are stored locally under `.maverick/do-task/<TASK-ID>/` and committed to version control.
- New `do-docs` workflow skill with three modes: greenfield (undocumented repos), refactor (non-compliant docs), and update (incremental changes after code diffs) — auto-detects mode when not specified
- Mono-repo support for the `upskill` skill — detects workspace configurations, enumerates packages, and generates per-package project skills at `<package>/docs/maverick/skills/<topic>/SKILL.md`
- Mono-repo support for `tech-docs` — repository type detection, package-level documentation paths, and mono-repo-aware file organisation rules
- Cross-cutting vs package-scoped topic classification for mono-repo skill generation

### Changed

- **Improved repo release workflow** - The release workflow previously involved increasing the semver value in main, then merging back to develop. This caused issues when trying to use a develop version of the plugin in Claude Code. The new process increases the semver in develop and then merges to main when releasing to production.
- **Jinja2 templating** — all skill and agent templates (`.md.j2`) now use Jinja2. Skills and agents reference each other via `{{ SKILLS.<CONSTANT> }}` and `{{ AGENTS.<CONSTANT> }}` variables, replacing static name strings. The full `SKILLS` and `AGENTS` dicts (built from `names.py`) are available in every template.
- **Simplified workflow pipeline** — replaced the three-layer decomposition (solution design → implementation plan → task breakdown) with a two-layer flow (solution design → create tasks). Removed `create-implementation-plan`, `mav-issue-breakdown`, and `mav-task-breakdown` skills.
- All three workflow skills (`do-issue-solo`, `do-issue-guided`, `do-task-solo`) now use a single "Create Tasks" phase instead of separate "Implementation Plan" and "Evaluate Plan Scope" phases
- Planner agents (`github-issue-planner`, `task-planner`) now produce task lists directly from the solution design instead of detailed implementation plans
- `mav-plan-execution` simplified — removed sub-task awareness section, updated terminology from "steps" to "tasks"
- Refactored `tech-docs` from user-invocable workflow to non-invocable standards reference skill — process/orchestration logic moved to `do-docs`, standards content (document structure, writing style, file organisation, diagrams, validation) retained
- Updated `tech-docs-writer` agent to depend on both `do-docs` (task orchestration) and `tech-docs` (standards)
- `do-issue-solo` Phase 7 now dispatches the `tech-docs-writer` agent with explicit `Mode: update`
- `init` skill now invokes `/maverick:do-docs` instead of `/maverick:tech-docs`
- Simplified README — removed outdated CLI examples, fixed typos, updated project init instructions
- Updated `architecture.md`, `overview.md`, `maverick-build.md`, and `claude-code-error-handling-and-recovery.md` to reflect the Jinja2 migration and simplified workflow pipeline
- Makefile `generate-skills` and `generate-agents` targets merged into a single `generate` target
- Skill and agent source directories renamed to match their config names (e.g., `create-solution-design/` → `mav-create-solution-design/`, agent dirs now include `agent-` prefix)

### Removed

- `create-implementation-plan` skill — replaced by `create-tasks`
- `mav-issue-breakdown` skill — functionality folded into `create-tasks` (sub-issues for >= 5 tasks)
- `mav-task-breakdown` skill — functionality folded into `create-tasks`

## [0.3.0] - 2026-03-10

## [0.2.0] - 2026-03-06

## [0.1.0-alpha] - 2026-03-04

### Added

- Claude Code plugin with 24 markdown skills and 2 agents
- Workflow skills: `do-issue-solo`, `do-issue-guided`, `upskill`, `maverick-alignment`, `tech-docs`
- Best-practice skills for logging, alerting, linting, unit testing, integration testing, CI/CD, git workflow, and scope boundaries
- Autonomous agents: `code-reviewer` and `tech-docs-writer`
- Python CLI with commands: `init`, `plugin`, `clean`, `build-ami`, `instance`, `infra`, `worker`
- Project initialisation with automatic tech stack detection
- Plugin management and packaging via `src/maverick/skills/`
- AWS infrastructure provisioning support
- Enforcement chain: best-practice skill → project skill → local verification → CI pipeline → agent review → human review

[Unreleased]: https://github.com/thermiteau/maverick/compare/v2.0.2...HEAD
[2.0.2]: https://github.com/thermiteau/maverick/compare/v2.0.1...v2.0.2
[2.0.1]: https://github.com/thermiteau/maverick/compare/v2.0.0...v2.0.1
[2.0.0]: https://github.com/thermiteau/maverick/compare/v1.0.3...v2.0.0
[1.0.3]: https://github.com/thermiteau/maverick/compare/v1.0.2...v1.0.3
[1.0.2]: https://github.com/thermiteau/maverick/compare/v1.0.1...v1.0.2
[1.0.1]: https://github.com/thermiteau/maverick/compare/v1.0.0...v1.0.1
[1.0.0]: https://github.com/thermiteau/maverick/compare/v0.5.7...v1.0.0
[0.5.7]: https://github.com/thermiteau/maverick/compare/v0.5.3...v0.5.7
[0.5.5]: https://github.com/thermiteau/maverick/compare/v0.5.3...v0.5.5
[0.5.3]: https://github.com/thermiteau/maverick/compare/v0.5.1...v0.5.3
[0.5.1]: https://github.com/thermiteau/maverick/compare/v0.4.0...v0.5.1
[0.4.0]: https://github.com/thermiteau/maverick/compare/v0.3.0...v0.4.0
[0.3.0]: https://github.com/thermiteau/maverick/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/thermiteau/maverick/compare/v0.1.0-alpha...v0.2.0
[0.1.0-alpha]: https://github.com/thermiteau/maverick/releases/tag/v0.1.0-alpha
