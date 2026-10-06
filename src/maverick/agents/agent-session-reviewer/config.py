from maverick.models import AgentConfig, ClaudeAgentOptions
from maverick.names import AGENT_SESSION_REVIEWER

CONFIG = AgentConfig(
    name=AGENT_SESSION_REVIEWER,
    description=(
        "Reviews {{ RUNTIME.NAME }} session activity and git diffs to identify "
        "missed opportunities, duplicated code, and quality issues."
    ),
    # Pure transcript/diff analysis.
    read_only=True,
    claude=ClaudeAgentOptions(
        # Transcript/diff analysis — a haiku-class task.
        model="haiku",
        color="magenta",
        # Nothing blocks on the review result — run it as a background task.
        background=True,
        # Accumulate cross-session findings (recurring skill gaps, repeated
        # duplication patterns) in persistent project memory.
        memory="project",
    ),
)
