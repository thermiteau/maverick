---
name: mav-local-verification
description: Pre-push code quality verification — lint, typecheck, and tests run locally before pushing. Covers discovering project verification commands, run order, scope-appropriate checks, and fixing failures. Used as a dependency from workflow skills.
user-invocable: false
disable-model-invocation: true
---

# Local Verification

Run lint, typecheck, and tests locally before every push. Never push code that fails local checks.

## Principles

1. **Verify locally first** — never push code that fails lint, typecheck, or tests
2. **Never skip git hooks** — never use `--no-verify` with git commands
3. **Fix before proceeding** — stop at the first failure, fix it, then continue

## Process

```dot
digraph verify {
    "Ready to push?" [shape=diamond];
    "Discover verification commands" [shape=box];
    "Run lint" [shape=box];
    "Lint passes?" [shape=diamond];
    "Fix lint issues" [shape=box];
    "Run typecheck" [shape=box];
    "Typecheck passes?" [shape=diamond];
    "Fix type errors" [shape=box];
    "Run tests" [shape=box];
    "Tests pass?" [shape=diamond];
    "Fix failing tests" [shape=box];
    "Push to remote" [shape=box];

    "Ready to push?" -> "Discover verification commands" [label="yes"];
    "Discover verification commands" -> "Run lint";
    "Run lint" -> "Lint passes?";
    "Lint passes?" -> "Run typecheck" [label="yes"];
    "Lint passes?" -> "Fix lint issues" [label="no"];
    "Fix lint issues" -> "Run lint";
    "Run typecheck" -> "Typecheck passes?";
    "Typecheck passes?" -> "Run tests" [label="yes"];
    "Typecheck passes?" -> "Fix type errors" [label="no"];
    "Fix type errors" -> "Run typecheck";
    "Run tests" -> "Tests pass?";
    "Tests pass?" -> "Push to remote" [label="yes"];
    "Tests pass?" -> "Fix failing tests" [label="no"];
    "Fix failing tests" -> "Run tests";
}
```

## Discovering Verification Commands

Projects use different tooling. Discover the available commands by checking these sources in order:

1. **`package.json` scripts** (Node.js projects):
   ```bash
   cat package.json | jq '.scripts | keys[]' 2>/dev/null
   ```
   Look for: `lint`, `typecheck`, `type-check`, `tsc`, `test`, `test:unit`, `check`

2. **`Makefile` targets**:
   ```bash
   grep -E '^[a-zA-Z_-]+:' Makefile 2>/dev/null
   ```
   Look for: `lint`, `check`, `test`, `verify`, `validate`

3. **Monorepo root** (if applicable):
   ```bash
   cat package.json | jq '.scripts' 2>/dev/null
   ```
   Look for workspace-level commands like `test:all`, `lint:all`, or use the package manager's workspace filter.

4. **Common patterns** if no scripts are found:

   | Tool | Lint | Typecheck | Test |
   |---|---|---|---|
   | npm/pnpm | `pnpm lint` | `pnpm typecheck` | `pnpm test` |
   | Turborepo | `pnpm turbo lint` | `pnpm turbo typecheck` | `pnpm turbo test` |
   | Make | `make lint` | `make typecheck` | `make test` |
   | Python (uv) | `uv run ruff check` | `uv run mypy .` | `uv run pytest` |
   | Go | `golangci-lint run` | (built into compile) | `go test ./...` |

## Running Verification

Run in this order — each stage catches different classes of issues:

1. **Lint** — catches style issues, unused imports, formatting
2. **Typecheck** — catches type errors, missing properties, wrong arguments
3. **Tests** — catches logic errors, regressions, broken integrations
4. **Project checks** — the project's invariant scripts (rules such as
   "every route declares a capability" or "nothing deletes from a
   retract-only table"), configured in `.maverick/config.json` under
   `checks.commands`:
   ```bash
   uv run maverick checks run --base "$(uv run maverick git-workflow story-base)"
   ```
   `--base` reads the checks from the base branch's committed config, so
   a change on your branch can never alter the checks that gate it. It
   exits 0 with a notice when none are configured. A failing check is
   a failed verification like any other: fix the code, never the check,
   unless the issue explicitly changes the invariant.

Stop at the first failure. Fix it before proceeding to the next stage.

## Scope-Appropriate Verification

Not every change needs the full suite:

| Change type | Lint | Typecheck | Tests | Project checks |
|---|---|---|---|---|
| Code changes | Yes | Yes | Yes — at minimum the affected test files | Yes |
| Config/YAML only | No | No | No (unless config affects runtime) | Yes |
| Documentation only | No | No | No | No |
| New dependencies added | Yes | Yes | Yes — full suite | Yes |

For the final push before PR creation, always run the full suite regardless of change type.

<!-- maverick-plugin-version: 5.2.1 -->
