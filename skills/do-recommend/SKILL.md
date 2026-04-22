---
name: do-recommend
description: Scan a project for missing best-practice areas and recommend 1-3 technology options for each gap. Currently covers linting and unit testing. Writes recommendations to docs/maverick/recommendations/<topic>.md.
argument-hint: topic to recommend (optional — processes all topics if omitted)
user-invocable: true
disable-model-invocation: false
---

**Depends on:** mav-bp-linting, mav-bp-unit-testing

# Recommend Best-Practice Technologies

Scan the current project for missing best-practice areas and produce a short-list of 1–3 technology recommendations for each gap. Output is a recommendation file per topic, not an implementation.

## Topics

| Topic | Best-Practice Skill | What to detect |
| ----- | ------------------- | -------------- |
| linting | mav-bp-linting | Linter configs, formatter configs, lint scripts, pre-commit hooks |
| unit-testing | mav-bp-unit-testing | Test frameworks, test runners, coverage tools, test files |

## Invocation

When invoked, process **all topics** in the table above unless `` names a specific topic — in that case process only that topic. Do not prompt the user for which topics to process.

## Process

For each topic:

### 1. Check Whether the Practice Already Exists

Scan for evidence that the practice is already in place:

**Linting:**
- Config files: `eslint.config.*`, `.eslintrc*`, `.prettierrc*`, `prettier.config.*`, `ruff.toml`, `pyproject.toml [tool.ruff]`, `.golangci.yml`, `.stylelintrc*`
- Package dependencies containing `eslint`, `prettier`, `ruff`, `clippy`, `golangci-lint`, `rubocop`, `stylelint`
- CI steps that run lint or format checks

**Unit testing:**
- Config files: `jest.config.*`, `vitest.config.*`, `pytest.ini`, `pyproject.toml [tool.pytest]`, `setup.cfg [tool:pytest]`
- Package dependencies containing `vitest`, `jest`, `mocha`, `pytest`, `unittest`, `junit`, `rspec`
- Test files: `**/*.test.*`, `**/*.spec.*`, `**/test_*.*`
- CI steps that run tests

If the practice is **already implemented** (configs exist, dependencies present, tests/rules are actively used), skip the topic and note it as already covered.

### 2. Identify the Project's Tech Stack

Determine the primary language(s) and framework(s) by reading:
- `package.json` (Node/JS/TS, look at framework deps like react, vue, express, etc.)
- `pyproject.toml` / `requirements.txt` (Python)
- `go.mod` (Go)
- `Cargo.toml` (Rust)
- `build.gradle.kts` / `pom.xml` (JVM)
- Source file extensions and directory structure

### 3. Read the Best-Practice Skill

Read the corresponding best-practice skill (e.g., `skills/mav-bp-linting/SKILL.md`) to understand the recommended tool categories and language-specific defaults.

### 4. Generate Recommendations

For the detected stack, recommend **1 to 3 concrete technology options** ranked by fit. Each recommendation must include:

- **Name** — the tool/library name
- **Why it fits** — 1–2 sentences explaining why this is a good match for the specific project stack
- **Getting started** — the single install command and minimal config needed
- **Trade-offs** — what it does well and what it lacks compared to alternatives

If there is a clear best choice for the stack (e.g., Ruff for Python, ESLint for TypeScript), recommend only 1 option. Only list alternatives when there are genuinely competitive options for the project's context.

### 5. Write the Recommendation File

Write to `docs/maverick/recommendations/<topic>.md` using the Write tool:

```markdown
---
name: <topic>
title: <Topic> — Technology Recommendations
generated: <YYYY-MM-DD>
status: pending
---

# <Topic> Recommendations

**Project stack:** <detected language(s) and framework(s)>

## Current State

<1–2 sentences describing what exists (or doesn't) for this practice area.>

## Recommendations

### 1. <Tool Name> (Recommended)

**Why it fits:** <1–2 sentences>

**Getting started:**
\```bash
<install command>
\```

**Minimal config:** <describe the config file and its key settings in prose — no code blocks>

**Trade-offs:** <strengths and limitations>

### 2. <Tool Name> (Alternative)

<same structure — only include if there is a genuinely competitive alternative>

### 3. <Tool Name> (Alternative)

<same structure — only include if there is a third viable option>

## Next Steps

To adopt the recommended option, run `/maverick:do-adopt <topic>`.
```

## Rules

- **Prose only** — describe configs and commands, don't dump config file contents
- **Stack-specific** — recommendations must match the project's actual language and framework, not generic advice
- **Honest trade-offs** — every tool has limitations, state them
- **Skip covered topics** — if the practice already exists, don't write a recommendation file. Print a message: `<topic>: already implemented, skipping.`
- **No implementation** — this skill recommends, it does not install or configure anything
- **Frontmatter required** — name, title, generated, status fields mandatory
- **Write directly** — no user approval needed, file is version-controlled

<!-- maverick-plugin-version: 0.5.7 -->
