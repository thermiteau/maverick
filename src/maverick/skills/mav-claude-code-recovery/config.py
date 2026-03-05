from maverick.models import SkillConfig
from maverick.names import MAV_CLAUDE_CODE_RECOVERY

CONFIG = SkillConfig(
    name=MAV_CLAUDE_CODE_RECOVERY,
    description=(
        "Patterns for Claude Code workflow resilience — state persistence, crash recovery, command failure handling, subagent failure handling, and artefact durability. Not about application-level error handling."
    ),
    user_invocable=False,
    disable_model_invocation=False,
    depends_on=[],
)
