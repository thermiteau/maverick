# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.2.0] - 2026-03-06

### Added

- New `do-docs` workflow skill with three modes: greenfield (undocumented repos), refactor (non-compliant docs), and update (incremental changes after code diffs) — auto-detects mode when not specified
- Mono-repo support for the `upskill` skill — detects workspace configurations, enumerates packages, and generates per-package project skills at `<package>/docs/maverick/skills/<topic>/SKILL.md`
- Mono-repo support for `tech-docs` — repository type detection, package-level documentation paths, and mono-repo-aware file organisation rules
- Cross-cutting vs package-scoped topic classification for mono-repo skill generation

### Changed

- Refactored `tech-docs` from user-invocable workflow to non-invocable standards reference skill — process/orchestration logic moved to `do-docs`, standards content (document structure, writing style, file organisation, diagrams, validation) retained
- Updated `tech-docs-writer` agent to depend on both `do-docs` (task orchestration) and `tech-docs` (standards)
- `do-issue-solo` Phase 7 now dispatches the `tech-docs-writer` agent with explicit `Mode: update`
- `init` skill now invokes `/maverick:do-docs` instead of `/maverick:tech-docs`
- Simplified README — removed outdated CLI examples, fixed typos, updated project init instructions

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

[Unreleased]: https://github.com/thermiteau/maverick/compare/v0.2.0...HEAD
[0.1.0-alpha]: https://github.com/thermiteau/maverick/releases/tag/v0.1.0-alpha
