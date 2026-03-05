from maverick.models import SkillConfig
from maverick.names import MAV_LOCAL_VERIFICATION

CONFIG = SkillConfig(
    name=MAV_LOCAL_VERIFICATION,
    description=(
        "Pre-push code quality verification — lint, typecheck, and tests run locally before pushing. Covers discovering project verification commands, run order, scope-appropriate checks, and fixing failures. Used as a dependency from workflow skills."
    ),
    user_invocable=False,
    disable_model_invocation=False,
    depends_on=[],
)
