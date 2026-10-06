---
title: Kiro
scope: Running Maverick's mechanical enforcement in Kiro
relates-to:
  - scope-boundaries.md
  - maverick-build.md
last-verified: 2026-10-06
---

# Kiro

Maverick's scope guard runs in [Kiro](https://kiro.dev) as a project hook. The policy is the same one Claude Code uses; only the delivery differs. Skills and agents for Kiro are not shipped yet.

## Set up

Install the CLI (`uv tool install maverick-harness`), then in the project:

```bash
maverick init --runtime kiro            # Kiro only
maverick init --runtime claude --runtime kiro   # both runtimes
```

This writes `.kiro/hooks/maverick.json`. Commit it so everyone working in the repo gets the guard. Kiro runs project hooks for every agent in the workspace, and it always asks before an agent writes to `.kiro/hooks/`, so an agent cannot quietly disable the guard. `maverick clean` removes the file (only if Maverick generated it).

## What it enforces

| Hook | Trigger | Does |
|---|---|---|
| `maverick-scope-guard` | `PreToolUse` | Runs `maverick hook scope-guard --runtime kiro` on every tool call: destructive git, commits/pushes on protected branches, infrastructure edits, production patterns, and writes to `.maverick/session-auth.json` |
| `maverick-session-release` | `SessionEnd` | Releases any issue claims this session still holds |

## Differences from Claude Code

- **No "ask".** Kiro hooks can only allow or block. Where Claude Code asks you in an interactive session, Kiro blocks and tells the agent to hand the action back to you: run it yourself, or record issue-level authorization with `maverick coord authorize`. Autonomous runs and production patterns block in both runtimes.
- **No subagent bookkeeping.** Kiro has no subagent start/stop hook events, so `do-issue-solo` timing reports don't record agent dispatches under Kiro.
- **V3 engine.** Hooks are written for Kiro CLI's V3 engine (`--agent-engine v3`) and the IDE's standalone hook format. V2 payloads are still understood.
- **POSIX shell.** The hook command is a POSIX `sh` one-liner; Kiro CLI on Windows is untested.

## Failure model

The hook must never block every tool call by accident. `maverick hook --runtime kiro` signals "block" with exit code 42, and the generated hook command maps only that code to Kiro's block code (2). Anything else — `maverick` not on `PATH`, a CLI too old to know `--runtime kiro`, an internal error — exits 0, and the tool call proceeds with a warning. Keep the CLI current with `uv tool install --force maverick-harness` so the guard stays active.
