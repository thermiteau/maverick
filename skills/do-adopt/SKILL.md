---
name: do-adopt
description: Scan a project for missing best-practice areas and implement the top recommendation for each gap. Currently covers linting and unit testing. Installs tools, writes configs, and adds CI steps.
argument-hint: topic to adopt (optional — processes all topics if omitted)
user-invocable: true
disable-model-invocation: false
---

**Depends on:** do-recommend, mav-bp-linting, mav-bp-unit-testing, mav-git-workflow, mav-local-verification

# Adopt Best-Practice Technologies

Scan the current project for missing best-practice areas and **implement the top recommendation** for each gap. This is the action counterpart to `do-recommend` — instead of listing options, it installs and configures the best-fit tool directly.

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

Use the same detection logic as do-recommend:

**Linting:**
- Config files: `eslint.config.*`, `.eslintrc*`, `.prettierrc*`, `prettier.config.*`, `ruff.toml`, `pyproject.toml [tool.ruff]`, `.golangci.yml`, `.stylelintrc*`
- Package dependencies containing `eslint`, `prettier`, `ruff`, `clippy`, `golangci-lint`, `rubocop`, `stylelint`
- CI steps that run lint or format checks

**Unit testing:**
- Config files: `jest.config.*`, `vitest.config.*`, `pytest.ini`, `pyproject.toml [tool.pytest]`, `setup.cfg [tool:pytest]`
- Package dependencies containing `vitest`, `jest`, `mocha`, `pytest`, `unittest`, `junit`, `rspec`
- Test files: `**/*.test.*`, `**/*.spec.*`, `**/test_*.*`
- CI steps that run tests

If the practice is **already implemented**, skip the topic. Print: `<topic>: already implemented, skipping.`

### 2. Identify the Project's Tech Stack

Determine the primary language(s) and framework(s) by reading:
- `package.json` (Node/JS/TS, look at framework deps like react, vue, express, etc.)
- `pyproject.toml` / `requirements.txt` (Python)
- `go.mod` (Go)
- `Cargo.toml` (Rust)
- `build.gradle.kts` / `pom.xml` (JVM)
- Source file extensions and directory structure

### 3. Read the Best-Practice Skill

Read the corresponding best-practice skill (e.g., `skills/mav-bp-linting/SKILL.md`) to understand the recommended tools and configuration standards for the detected stack.

### 4. Check for Existing Recommendation

If `docs/maverick/recommendations/<topic>.md` exists and has `status: pending`, read it and use the top recommendation (the one marked "Recommended"). This avoids re-analysing the stack when `do-recommend` was already run.

If no recommendation file exists, determine the top recommendation directly from the best-practice skill's language-specific defaults table.

### 5. Implement the Top Recommendation

Install and configure the recommended tool. Follow the best-practice skill's standards precisely.

**For linting — implement all of:**

1. **Install packages** — add the linter and formatter as dev dependencies using the project's package manager
2. **Create config file** — write the linter config at the project root using the recommended preset (e.g., `eslint.config.js` with flat config for TS/JS, `ruff.toml` for Python). Follow the error-only policy from the best-practice skill.
3. **Create formatter config** — if the formatter is a separate tool (e.g., Prettier for JS/TS), write its config. If the linter handles formatting (e.g., Ruff), configure it in the same file.
4. **Add ignore patterns** — exclude build output, generated code, and vendor directories
5. **Add package scripts** — add `lint` and `format` (or equivalent) scripts to the project's script runner (package.json scripts, Makefile, pyproject.toml scripts)
6. **Verify** — run the lint command and fix any initial errors in project source code. The goal is a clean lint pass, not a config that ignores existing issues.

**For unit testing — implement all of:**

1. **Install packages** — add the test framework and assertion library as dev dependencies
2. **Create config file** — write the test runner config at the project root with sensible defaults (e.g., `vitest.config.ts` for Vite projects, `jest.config.js` for other JS/TS, `pyproject.toml [tool.pytest]` for Python)
3. **Create a sample test** — write one example test file demonstrating the project's test conventions (file location, import pattern, describe/it structure). Place it alongside or mirroring an existing source file. The test should verify real behaviour, not be a trivial placeholder.
4. **Add package scripts** — add a `test` script (and `test:coverage` if the framework supports it)
5. **Verify** — run the test suite and confirm the sample test passes

### 6. Update the Recommendation File

If a recommendation file exists at `docs/maverick/recommendations/<topic>.md`, update its `status` from `pending` to `adopted`. If no recommendation file exists, create one with `status: adopted` using the same structure as do-recommend but with only the implemented option.

### 7. Commit the Changes

Create a conventional commit for each topic adopted:

```
chore: adopt <tool-name> for <topic> (<topic>)
```

Follow the mav-git-workflow skill for commit conventions. Do not push — the user will review and push.

## Rules

- **Best-practice compliant** — every config choice must follow the corresponding best-practice skill. Do not deviate from the standards (error-only policy, separate linter/formatter, etc.).
- **Stack-specific** — install and configure tools that match the project's actual language and framework
- **Minimal and correct** — write the minimum config needed for a clean, working setup. Do not add rules or plugins beyond the recommended preset.
- **Verify before committing** — run the tool after installation. If it fails, fix the issue. Do not commit a broken setup.
- **Skip covered topics** — if the practice already exists, do not overwrite or reconfigure it
- **No branch creation** — commit directly to the current branch. The user is expected to be on an appropriate branch.
- **One commit per topic** — separate commits make it easy to review or revert individual adoptions

<!-- maverick-plugin-version: 2.0.3-dev -->
