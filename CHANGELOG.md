# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- New `task-breakdown` skill — decomposes large implementation plans (>8 steps) into independently trackable sub-tasks with dependency ordering and file ownership tracking. Groups steps by shared file adjacency, enforces a maximum of 4 steps per sub-task, and validates complete coverage with no circular dependencies. Supports two modes: `local` (creates `breakdown.json` and `sub-tasks/` directory for do-task-solo) and `issue` (creates GitHub sub-issues linked to the parent issue for do-issue-solo/guided)
- New `do-issue-guided` workflow skill — interactive counterpart to `do-issue-solo`. Works through the same phases (understand → design → plan → branch → implement → review → push → PR) but pauses at four checkpoints (design review, plan review, review results, completion) for user confirmation. Proceeds autonomously between checkpoints.
- New `do-task-solo` workflow skill — autonomous end-to-end task execution without GitHub issues. The user describes what they want interactively, and Claude formalises it as a structured task document, then designs, plans, and implements it. All artifacts (task description, design, plan, completion) are stored locally under `.maverick/do-tasks/<TASK-ID>/` and committed to version control.
- New `do-docs` workflow skill with three modes: greenfield (undocumented repos), refactor (non-compliant docs), and update (incremental changes after code diffs) — auto-detects mode when not specified
- Mono-repo support for the `upskill` skill — detects workspace configurations, enumerates packages, and generates per-package project skills at `<package>/docs/maverick/skills/<topic>/SKILL.md`
- Mono-repo support for `tech-docs` — repository type detection, package-level documentation paths, and mono-repo-aware file organisation rules
- Cross-cutting vs package-scoped topic classification for mono-repo skill generation

### Changed

- `create-implementation-plan` scope threshold simplified from 8-10 steps to a hard 8-step limit. Plans exceeding 8 steps now produce the complete plan and delegate decomposition to the `task-breakdown` skill, replacing the previous manual phase-splitting approach
- All three workflow skills (`do-issue-solo`, `do-issue-guided`, `do-task-solo`) now include Phase 3.5 (Evaluate Plan Scope) which invokes `task-breakdown` when plans exceed 8 steps, and Phase 5 conditionally executes sub-tasks in dependency order when a breakdown exists
- `mav-plan-execution` now supports sub-task awareness — loads sub-task-scoped plans, tracks progress per sub-task, uses dual-reference commit messages (e.g., `feat: ... (TASK-001/ST-001)`), and includes sub-task crash recovery
- `do-task-solo` crash recovery updated to detect and resume from incomplete sub-tasks using `breakdown.json` and sub-task `plan.md` checkboxes
- Refactored `tech-docs` from user-invocable workflow to non-invocable standards reference skill — process/orchestration logic moved to `do-docs`, standards content (document structure, writing style, file organisation, diagrams, validation) retained
- Updated `tech-docs-writer` agent to depend on both `do-docs` (task orchestration) and `tech-docs` (standards)
- `do-issue-solo` Phase 7 now dispatches the `tech-docs-writer` agent with explicit `Mode: update`
- `init` skill now invokes `/maverick:do-docs` instead of `/maverick:tech-docs`
- Simplified README — removed outdated CLI examples, fixed typos, updated project init instructions
- Updated `architecture.md`, `overview.md`, and `claude-code-error-handling-and-recovery.md` to cover the new `do-issue-guided` and `do-task-solo` workflows — added workflow entry point diagram, local task state persistence, and artefact durability patterns for committed task files

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

[Unreleased]: https://github.com/thermiteau/maverick/compare/v0.1.0-alpha...HEAD
[0.1.0-alpha]: https://github.com/thermiteau/maverick/releases/tag/v0.1.0-alpha
