from maverick.models import SkillConfig
from maverick.names import MAV_BP_TASK_TRACKING

CONFIG = SkillConfig(
    name=MAV_BP_TASK_TRACKING,
    description=(
        "Task tracking and management conventions for all projects. Covers the requirement for external task tracking, issue hygiene, workflow integration, and traceability between tasks and code changes. Applied as a foundational project management requirement."
    ),
    user_invocable=False,
    disable_model_invocation=True,
    depends_on=[],
)
