"""CLI handler for `maverick agent-model` (#181).

Prints the model a workflow should dispatch an agent on, from the
``agent_models`` map in ``.maverick/config.json`` (repo) merged over
``~/.maverick/config.json`` (user). Workflow skills call it before each
dispatch and pass a non-empty result as the dispatch's ``model`` override.
An empty line means "no route": dispatch without an override, so the agent
keeps its own pinned model or inherits the caller's.
"""

from __future__ import annotations

import json
from argparse import Namespace

from maverick.config import read_agent_models


def main(args: Namespace) -> int:
    models = read_agent_models()
    if args.agent:
        model = models.get(args.agent, "")
        print(json.dumps({args.agent: model or None}) if args.json else model)
        return 0
    if args.json:
        print(json.dumps(models, indent=2, sort_keys=True))
    else:
        for agent in sorted(models):
            print(f"{agent}\t{models[agent]}")
    return 0
