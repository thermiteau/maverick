from maverick.models import SkillConfig
from maverick.names import MAV_PLAN_EXECUTION

CONFIG = SkillConfig(
    name=MAV_PLAN_EXECUTION,
    description=(
        "How to execute an implementation plan step-by-step. Covers the execution loop, verification discipline, failure handling, progress tracking, crash recovery, and acceptance criteria. Adapts behaviour based on whether the caller is solo (autonomous) or guided (human checkpoints). Used as a dependency from workflow skills."
    ),
    user_invocable=False,
    disable_model_invocation=False,
    depends_on=[],
)
