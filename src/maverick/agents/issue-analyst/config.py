from maverick.models import AgentConfig
from maverick.names import AGENT_ISSUE_ANALYST, CREATE_SOLUTION_DESIGN, MAV_GITHUB_ISSUE_WORKFLOW, MAV_SCOPE_BOUNDARIES

CONFIG = AgentConfig(
    name=AGENT_ISSUE_ANALYST,
    description=(
        "Reads a GitHub issue, explores the codebase, and produces a solution design."
        " Dispatched by do-issue-solo and do-issue-guided as a subagent so that"
        " codebase exploration does not consume the caller's context window."
    ),
    color="cyan",
    skills=[
        MAV_GITHUB_ISSUE_WORKFLOW,
        CREATE_SOLUTION_DESIGN,
        MAV_SCOPE_BOUNDARIES,
    ],
)
