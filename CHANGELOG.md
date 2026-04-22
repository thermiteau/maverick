# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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

[Unreleased]: https://github.com/thermiteau/maverick/compare/v0.5.5...HEAD
[0.5.5]: https://github.com/thermiteau/maverick/compare/v0.5.3...v0.5.5
[0.5.3]: https://github.com/thermiteau/maverick/compare/v0.5.1...v0.5.3
[0.5.1]: https://github.com/thermiteau/maverick/compare/v0.4.0...v0.5.1
[0.4.0]: https://github.com/thermiteau/maverick/compare/v0.3.0...v0.4.0
[0.3.0]: https://github.com/thermiteau/maverick/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/thermiteau/maverick/compare/v0.1.0-alpha...v0.2.0
[0.1.0-alpha]: https://github.com/thermiteau/maverick/releases/tag/v0.1.0-alpha
