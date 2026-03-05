from maverick.models import AgentConfig
from maverick.names import AGENT_ISSUE_PLANNER, CREATE_IMPLEMENTATION_PLAN, MAV_GITHUB_ISSUE_WORKFLOW, MAV_SCOPE_BOUNDARIES

CONFIG = AgentConfig(
    name=AGENT_ISSUE_PLANNER,
    description=(
        "Takes a solution design and produces an ordered implementation plan."
        " Dispatched by do-issue-solo and do-issue-guided as a subagent so that"
        " planning does not consume the caller's context window."
    ),
    color="green",
    skills=[
        MAV_GITHUB_ISSUE_WORKFLOW,
        CREATE_IMPLEMENTATION_PLAN,
        MAV_SCOPE_BOUNDARIES,
    ],
)
