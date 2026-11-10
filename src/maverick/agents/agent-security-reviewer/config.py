from maverick.models import AgentConfig, ClaudeAgentOptions
from maverick.names import (
    AGENT_SECURITY_REVIEWER,
    MAV_BP_APPLICATION_SECURITY,
    MAV_SCOPE_BOUNDARIES,
)

CONFIG = AgentConfig(
    name=AGENT_SECURITY_REVIEWER,
    description=(
        "Independent security reviewer for a story's diff. Runs in a fresh context"
        " (never the author's), applies the project's own security checklist from"
        " docs/maverick/skills/ on top of generic OWASP categories, runs the"
        " project's invariant checks, and returns PASS, FINDINGS or BLOCKING."
        " Dispatched by do-issue-solo and do-issue-guided as the mandatory"
        " pre-PR security gate."
    ),
    # A reviewer that can fix what it reviews stops being a gate: read-only.
    read_only=True,
    skills=[
        MAV_BP_APPLICATION_SECURITY,
        MAV_SCOPE_BOUNDARIES,
    ],
    claude=ClaudeAgentOptions(
        color="red",
        # Like the code reviewer, the security gate must not inherit a
        # cheaper caller model. Pin a strong model explicitly.
        model="opus",
    ),
)
