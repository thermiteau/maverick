---
name: do-init
description: Initialise a project for use with Maverick — installs the CLI if needed, writes the project config with integration tracking, scaffolds docs, generates project skills, and runs an initial cybersecurity audit.
user-invocable: true
---

# Init Maverick Project

Set up the current repository for Maverick — install the CLI if needed, write the project-level config (`.maverick/config.json` with detected modules and the integration tracking block), scaffold docs, and generate project skills.

## Dispatch

Dispatch the **agent-maverick** agent with task `init` and any user-provided arguments. The agent will follow the process below and return a structured result.

## Process

### 1. Ensure the Maverick CLI is installed and matches the plugin

Run `command -v maverick` to check whether the CLI is already on PATH.

**If `maverick` is not on PATH**, dispatch the **/maverick:do-install** skill and wait for it to complete. After the install returns, re-run `command -v maverick` to confirm the binary is now resolvable. If it still is not (e.g. `~/.local/bin` is not on the user's PATH), report the install message verbatim to the user and stop — they need to fix PATH and re-invoke `/maverick:do-init` manually.

**If `maverick` is on PATH**, verify the installed CLI matches the loaded plugin. A stale binary from an earlier plugin version can be missing subcommands the rest of this skill depends on (e.g. `maverick integration`, `maverick preflight`).

- Read the installed CLI version: `maverick --version`
- Read the plugin version: `grep -Po '(?<=^version = ")[^"]+' "${CLAUDE_PLUGIN_ROOT}/pyproject.toml"`
- If they differ, dispatch **/maverick:do-install** to refresh the CLI. That skill always runs `uv tool install --force` from the plugin root, so it overwrites whatever is currently installed. After it returns, re-run `maverick --version` and confirm it now matches the plugin version. If it still does not, surface the mismatch to the user and stop.
- If the versions already match, skip to step 2.

`do-init` cannot complete without a CLI version that matches the plugin. The remaining steps invoke `maverick` directly and depend on subcommands that may have been added in newer versions.

### 2. Initialise the project config

Run:

```bash
uv run maverick init
```

This detects the project's tech stack, writes `.maverick/config.json` with the detected modules and a fresh `integration` block (`init: true`, all other flags `false`), and prints a summary of what was detected. If a config already exists, the command preserves any integration flags that are already `true` — re-running is safe.

### 3. Initialise project-level overrides

Write `.maverick/settings.json` containing `{}` if the file does not already exist. This is where project-specific overrides go later; an empty object is the correct default. Do not overwrite an existing file.

### 4. Scaffold the technical documentation

Dispatch **/maverick:do-docs**. The greenfield mode of that skill flips `integration.tech_docs_scaffolded` to `true` automatically when it completes.

### 5. Generate project skills

Dispatch **/maverick:do-upskill**. It iterates every topic in `topics.json` and writes per-topic skills under `docs/maverick/skills/`, then flips `integration.upskill` to `true`.

### 6. Run the cybersecurity review

Dispatch **/maverick:do-cybersecurity-review**. It scans the existing codebase for common security risks (secrets, dependency vulnerabilities, auth/input-validation patterns), writes findings to `docs/security-audit.md`, and flips `integration.cybersecurity_reviewed` to `true`. The review is surface-only — it reports, it does not modify code. Any FAIL findings should be tracked as follow-up issues by the user.

### 7. Report

Print a final summary to the user:

- Detected modules (from step 2's output)
- Whether docs were scaffolded greenfield or already existed
- How many project skills were generated
- The number of security-audit findings at each severity, and the path to the audit report
- The current integration state: `uv run maverick integration get`

The integration checklist gives the user (and any future Maverick session) a clear view of what's been completed and what's still pending.

<!-- maverick-plugin-version: 1.0.4-dev -->
