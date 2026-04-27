"""CLI handlers for `maverick integration get` and `maverick integration set`.

Reads/writes the ``integration`` block of ``.maverick/config.json`` — the
per-project record of which Maverick adoption milestones have been carried
out. The file is committed to git, so the state is persisted across machines
and contributors.
"""

from __future__ import annotations

import json
import sys
from argparse import Namespace

from maverick.config import (
    CONFIG_DEFAULTS,
    project_config_path,
    read_integration_status,
    set_integration_flag,
)


def main(args: Namespace) -> None:
    if args.integration_action == "get":
        _handle_get(args)
    elif args.integration_action == "set":
        _handle_set(args)
    else:  # pragma: no cover — argparse 'required=True' should prevent this
        print("unknown integration action", file=sys.stderr)
        sys.exit(2)


def _handle_get(args: Namespace) -> None:
    status = read_integration_status()

    if args.key:
        if args.key not in status:
            _exit_unknown_key(args.key)
        if args.json:
            print(json.dumps({args.key: status[args.key]}, indent=2))
        else:
            print("true" if status[args.key] else "false")
        return

    if args.json:
        print(json.dumps(status, indent=2))
        return

    width = max(len(k) for k in status)
    for key in sorted(status):
        check = "[x]" if status[key] else "[ ]"
        print(f"{check} {key:<{width}}")


def _handle_set(args: Namespace) -> None:
    if not project_config_path().exists():
        print(
            f"No project config at {project_config_path()}. "
            "Run `maverick init` first.",
            file=sys.stderr,
        )
        sys.exit(1)

    value = args.value == "true"
    try:
        set_integration_flag(args.key, value)
    except KeyError:
        _exit_unknown_key(args.key)
    print(f"{args.key} = {args.value}")


def _exit_unknown_key(key: str) -> None:
    valid = sorted(CONFIG_DEFAULTS["integration"].keys())
    print(
        f"Unknown integration key: {key!r}. Valid keys: {', '.join(valid)}",
        file=sys.stderr,
    )
    sys.exit(2)
