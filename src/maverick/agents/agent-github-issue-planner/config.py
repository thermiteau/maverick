from maverick.models import AgentConfig
from maverick.names import (
    AGENT_GITHUB_ISSUE_PLANNER,
    MAV_CREATE_TASKS,
    MAV_GITHUB_ISSUE_WORKFLOW,
    MAV_SCOPE_BOUNDARIES,
)

CONFIG = AgentConfig(
    name=AGENT_GITHUB_ISSUE_PLANNER,
    description=(
        """Takes a solution design and produces an ordered task list. Dispatched by do-issue-solo and do-issue-guided as a subagent so that planning does not consume the caller's context window."""
    ),
    color="green",
    # Mechanical decomposition of an existing design — a haiku-class task.
    model="haiku",
    # Prose already says "do not modify source code" — enforce it.
    disallowed_tools=["Edit", "Write", "NotebookEdit"],
    skills=[
        MAV_GITHUB_ISSUE_WORKFLOW,
        MAV_CREATE_TASKS,
        MAV_SCOPE_BOUNDARIES,
    ],
)
