---
name: do-install
description: Install the maverick CLI tool system-wide at the version matching this plugin.
user-invocable: true
disable-model-invocation: false
context: fork
---

# Install Maverick CLI

Install the `maverick` CLI at the version that matches this plugin — from source in a local dev checkout, or the matching `maverick-harness` release from PyPI otherwise.

## Execution Context

This skill runs in its own forked context (`context: fork`) — you are
executing it directly; there is no separate agent to dispatch. Follow the
process below exactly and end with a structured result: task, SUCCESS or
FAILURE, what was done, and any warnings.

## Process

1. **Locate the plugin root.** If `${CLAUDE_PLUGIN_ROOT}` is set, use that. Otherwise resolve two levels above this `SKILL.md` (i.e. the parent of `skills/do-install/`). Fail with a clear error if `hooks/install_cli.py` is not found under the resolved path.

2. **Run the installer.** From a shell:

       python3 <plugin-root>/hooks/install_cli.py --plugin-root <plugin-root>

   The script (stdlib-only, so it runs before the CLI exists) performs the install procedure end-to-end:
   - verifies `uv` is on PATH
   - verifies `gh` (GitHub CLI) is on PATH — Maverick workflows depend on it for issue and PR operations; the installer fails with platform-specific install instructions if missing
   - decides what to install: the plugin root itself when it contains `pyproject.toml` (a source checkout), otherwise `maverick-harness==<plugin version>` from PyPI
   - removes the legacy `maverick` uv tool if present (the CLI's distribution was renamed to `maverick-harness`; the command is still `maverick`)
   - runs `uv tool install --force <source-or-release>`
   - verifies `maverick` is on PATH (warns about `~/.local/bin` if not)
   - adds `Read(~/.claude/plugins/cache/thermite/maverick/**)` to `~/.claude/settings.json` `permissions.allow` (idempotent)

3. **Verify.** Run `maverick --help` and capture the first line.

4. **Report.** Return a structured result: what was installed (source path or PyPI release), whether the settings file was modified or already had the permission entry, and any PATH warnings.

<!-- maverick-plugin-version: 5.0.1-dev -->
