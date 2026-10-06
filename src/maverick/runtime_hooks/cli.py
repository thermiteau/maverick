"""``maverick hook <handler> --runtime <name>`` — the CLI side of every hook.

Reads the runtime's native payload on stdin, normalizes it through the
runtime's adapter, runs the handler, and writes the runtime's native
response. Dispatched from ``maverick.cli.main`` *before* the full argument
parser is built, so a hook pays only for the imports it needs — it runs on
every tool call.

Exit codes: the adapter decides. Claude Code's adapter always exits 0 and
expresses decisions as JSON, because its plugin shim treats any non-zero
exit as "this CLI cannot run hooks" and fails open. Kiro's adapter signals a
block with ``KIRO_BLOCK_EXIT``, which the generated Kiro hook command maps to
Kiro's own "block" code. Internal errors and unparseable input always exit 0
(fail open, with a warning on stderr).
"""

from __future__ import annotations

import argparse
import json
import os
import sys

from maverick.runtime_hooks.adapters import ADAPTERS, HookOutput

HANDLERS = ("scope-guard", "subagent-report", "session-release")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="maverick hook",
        description="Run a Maverick hook handler on a runtime hook payload (stdin).",
    )
    parser.add_argument("handler", choices=HANDLERS)
    parser.add_argument("--runtime", choices=sorted(ADAPTERS), required=True)
    return parser


def run(handler: str, runtime: str, raw: dict, env: dict[str, str]) -> HookOutput:
    """Dispatch one normalized event. May raise; ``main`` fails open."""
    adapter = ADAPTERS[runtime]
    event = adapter.normalize(raw)

    if handler == "scope-guard":
        if env.get("MAVERICK_GUARD_DISABLE") == "1" or event.tool is None:
            return HookOutput()
        from maverick.runtime_hooks import scope_guard

        verdict = scope_guard.resolve(scope_guard.decide(event.tool), event.tool, env)
        return adapter.render_tool_decision(verdict.decision, verdict.reason)

    if handler == "subagent-report":
        from maverick.runtime_hooks import subagent_report

        subagent_report.handle(event, env)
        return HookOutput()

    from maverick.runtime_hooks import session_release

    return session_release.handle()


def main(argv: list[str]) -> int:
    try:
        args = _parser().parse_args(argv)
    except SystemExit as exc:
        # A handler or runtime this CLI doesn't know (version skew between
        # the CLI and the hook config) must fail open, not block every call.
        if exc.code in (0, None):
            raise
        print(
            "maverick hook: unrecognised arguments; hook skipped. The hook "
            "config may be newer than this CLI — upgrade maverick-harness.",
            file=sys.stderr,
        )
        return 0
    try:
        raw = json.loads(sys.stdin.read() or "{}")
        if not isinstance(raw, dict):
            raw = {}
    except json.JSONDecodeError:
        return 0  # unparseable input — fail open, never break the session

    try:
        out = run(args.handler, args.runtime, raw, dict(os.environ))
    except Exception as exc:  # noqa: BLE001 — fail open by contract
        print(f"maverick {args.handler}: internal error ({exc}); allowing.", file=sys.stderr)
        return 0

    if out.stdout:
        print(out.stdout)
    if out.stderr:
        sys.stderr.write(out.stderr)
    return out.exit_code
