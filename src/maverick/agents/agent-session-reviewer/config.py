from maverick.models import AgentConfig
from maverick.names import AGENT_SESSION_REVIEWER

CONFIG = AgentConfig(
    name=AGENT_SESSION_REVIEWER,
    description=(
        "Reviews Claude Code session activity and git diffs to identify "
        "missed opportunities, duplicated code, and quality issues."
    ),
    # Transcript/diff analysis — a haiku-class task; pure analysis, read-only.
    model="haiku",
    color="magenta",
    # Nothing blocks on the review result — run it as a background task.
    background=True,
    # Accumulate cross-session findings (recurring skill gaps, repeated
    # duplication patterns) in persistent project memory.
    memory="project",
    disallowed_tools=["Edit", "Write", "NotebookEdit"],
)
