"""CLI handler for `maverick preflight <skill>`.

Exits 0 when every prerequisite is satisfied, 1 when one or more are not,
2 for unknown skills (treated as a configuration error rather than an
unmet prerequisite).
"""

from __future__ import annotations

import dataclasses
import json
import sys
from argparse import Namespace

from maverick.preflight import evaluate, render_human


def main(args: Namespace) -> int:
    result = evaluate(args.skill)

    if args.json:
        payload = dataclasses.asdict(result)
        payload["passed"] = result.passed
        print(json.dumps(payload, indent=2))
    else:
        text = render_human(result)
        if result.passed:
            print(text)
        else:
            print(text, file=sys.stderr)

    if result.unknown_skill:
        return 2
    return 0 if result.passed else 1
