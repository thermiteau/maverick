from maverick.models import AgentConfig, ClaudeAgentOptions
from maverick.names import (
    AGENT_IMPLEMENTER,
    MAV_LOCAL_VERIFICATION,
    MAV_SCOPE_BOUNDARIES,
)

CONFIG = AgentConfig(
    name=AGENT_IMPLEMENTER,
    description=(
        "Implements one task, or one fix, of a story in its worktree: runs do-code,"
        " verifies locally, commits and pushes, then returns a short structured summary."
        " Dispatched by do-issue-solo once per task so that source files, test output"
        " and fix iterations never enter the story agent's context window."
    ),
    skills=[
        MAV_LOCAL_VERIFICATION,
        MAV_SCOPE_BOUNDARIES,
    ],
    claude=ClaudeAgentOptions(color="green"),
)
