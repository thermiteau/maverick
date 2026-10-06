---
title: Kiro
scope: Running Maverick's mechanical enforcement in Kiro
relates-to:
  - scope-boundaries.md
  - maverick-build.md
last-verified: 2026-10-06
---

# Kiro

Maverick runs in [Kiro](https://kiro.dev) with the same skills, agents and scope-guard policy as in Claude Code; only the delivery differs. The CLI installs everything, because Kiro has no plugin format that can carry agents or hooks (Powers hold only skills and MCP config).

## Set up

```bash
uv tool install maverick-harness   # the CLI
maverick kiro install              # skills and agents into ~/.kiro (once per machine)
cd <project>
maverick init --runtime kiro       # scope guard for this project
```

To use both runtimes in a project, run `maverick init --runtime claude --runtime kiro`.

## Skills and agents

`maverick kiro install` renders Maverick's 41 skills and 5 agents for Kiro from the sources shipped in the CLI, so they always match the CLI version, and installs them globally:

- **Skills** go to `~/.kiro/skills/<name>/`, in the open Agent Skills format. Invoke one as `/<name>` (for example `/do-issue-solo 42`), or let Kiro activate it from your request.
- **Agents** go to `~/.kiro/agents/<name>.md`, in Kiro's Markdown agent format, with their skills attached as `skill://` resources and the project's steering (`.kiro/steering/`) as a `file://` resource. The main agent delegates to them as sub-agents (for example `agent-code-reviewer`). Read-only agents (the reviewer, planner, analyst and session reviewer) have no write tools and a `deny` rule on `fs_write`.

`~/.kiro/maverick/manifest.json` records what was installed. Re-running `maverick kiro install` after upgrading the CLI updates the bundle and removes anything a newer version dropped. It never replaces a skill or agent of yours with the same name unless you pass `--force`. `maverick kiro status` reports the installed version and exits non-zero when it no longer matches the CLI; `maverick kiro uninstall` removes only Maverick's files.

In a Kiro session, `/do-init` sets the project up for Kiro: it runs `maverick init --runtime kiro` (the scope guard below) and `/do-upskill` writes its convention pointers as steering files in `.kiro/steering/`. Nothing is written under `.claude/`.

## Scope guard

`maverick init --runtime kiro` writes `.kiro/hooks/maverick.json`. Commit it so everyone working in the repo gets the guard. Kiro runs project hooks for every agent in the workspace, and it always asks before an agent writes to `.kiro/hooks/`, so an agent cannot quietly disable the guard. `maverick clean` removes the file (only if Maverick generated it).

## What it enforces

| Hook | Trigger | Does |
|---|---|---|
| `maverick-scope-guard` | `PreToolUse` | Runs `maverick hook scope-guard --runtime kiro` on every tool call: destructive git, commits/pushes on protected branches, infrastructure edits, production patterns, and writes to `.maverick/session-auth.json` |
| `maverick-session-release` | `SessionEnd` | Releases any issue claims this session still holds |

## Differences from Claude Code

- **No invocation flags.** Kiro skills have no equivalent of Claude Code's `user-invocable` / `disable-model-invocation`, so every Maverick skill is both a `/name` command and model-activatable.
- **Models.** Agents use your Kiro model; Claude Code's per-agent model pins (`opus`, `haiku`) are not carried over.
- **No "ask".** Kiro hooks can only allow or block. Where Claude Code asks you in an interactive session, Kiro blocks and tells the agent to hand the action back to you: run it yourself, or record issue-level authorization with `maverick coord authorize`. Autonomous runs and production patterns block in both runtimes.
- **Guarded inside sub-agents too.** Project hooks and an agent's permission rules both apply to tool calls a sub-agent makes, so delegating to a Maverick agent doesn't route around the guard (verified in Kiro CLI 2.27.1, V3 engine).
- **No subagent bookkeeping.** Kiro has no subagent start/stop hook events, so `do-issue-solo` timing reports don't record agent dispatches under Kiro.
- **V3 engine.** Hooks are written for Kiro CLI's V3 engine (`--agent-engine v3`) and the IDE's standalone hook format. V2 payloads are still understood.
- **POSIX shell.** The hook command is a POSIX `sh` one-liner; Kiro CLI on Windows is untested.

## Failure model

The hook must never block every tool call by accident. `maverick hook --runtime kiro` signals "block" with exit code 42, and the generated hook command maps only that code to Kiro's block code (2). Anything else — `maverick` not on `PATH`, a CLI too old to know `--runtime kiro`, an internal error — exits 0, and the tool call proceeds with a warning. Keep the CLI current with `uv tool install --force maverick-harness` so the guard stays active.
