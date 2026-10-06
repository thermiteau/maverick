from maverick.models import AgentConfig, ClaudeAgentOptions
from maverick.names import (
    AGENT_CODE_REVIEWER,
    MAV_BP_CODE_REVIEW,
    MAV_BP_OPERABILITY,
    MAV_BP_TESTING,
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
    # A reviewer that can fix what it reviews stops being a gate: read-only.
    read_only=True,
    skills=[
        MAV_BP_CODE_REVIEW,
        MAV_BP_OPERABILITY,
        MAV_BP_TESTING,
        MAV_SCOPE_BOUNDARIES,
    ],
    claude=ClaudeAgentOptions(
        color="yellow",
        # The merge gate must not inherit whatever model the caller runs — a
        # cost-conscious session would silently weaken the highest-stakes
        # judgment in the system. Pin a strong model explicitly.
        model="opus",
    ),
)
