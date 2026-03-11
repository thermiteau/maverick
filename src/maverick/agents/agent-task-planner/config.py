from maverick.models import AgentConfig
from maverick.names import (
    AGENT_TASK_PLANNER,
    MAV_CREATE_TASKS,
    MAV_SCOPE_BOUNDARIES,
)

CONFIG = AgentConfig(
    name=AGENT_TASK_PLANNER,
    description=(
        """Takes a solution design and produces an ordered task list.
        Dispatched by do-task-solo as a subagent so that planning does not consume the caller's context window."""
    ),
    color="green",
    skills=[
        MAV_CREATE_TASKS,
        MAV_SCOPE_BOUNDARIES,
    ],
)
