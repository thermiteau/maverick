from maverick.models import AgentConfig
from maverick.names import AGENT_SESSION_REVIEWER

CONFIG = AgentConfig(
    name=AGENT_SESSION_REVIEWER,
    description=(
        "Reviews Claude Code session activity and git diffs to identify "
        "missed opportunities, duplicated code, and quality issues."
    ),
    model="sonnet",
    color="magenta",
)
