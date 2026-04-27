from maverick.models import AgentConfig
from maverick.names import (
    AGENT_CODE_REVIEWER,
    MAV_BP_ALERTING,
    MAV_BP_LOGGING,
    MAV_SCOPE_BOUNDARIES,
)

CONFIG = AgentConfig(
    name=AGENT_CODE_REVIEWER,
    description=(
        "Autonomous code reviewer that performs two-stage review — spec compliance"
        " first, then code quality (correctness, test coverage, maintainability)."
        " Security is out of scope; do-cybersecurity-review handles that as a"
        " mandatory pre-push gate. Dispatched after completing implementation"
        " steps or before creating PRs."
    ),
    color="yellow",
    skills=[
        MAV_BP_LOGGING,
        MAV_BP_ALERTING,
        MAV_SCOPE_BOUNDARIES,
    ],
)
