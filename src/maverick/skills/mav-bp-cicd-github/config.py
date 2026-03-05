from maverick.models import SkillConfig
from maverick.names import MAV_BP_CICD_GITHUB

CONFIG = SkillConfig(
    name=MAV_BP_CICD_GITHUB,
    description=(
        "Monitoring GitHub Actions pipelines after pushing. Covers checking workflow status, diagnosing CI failures, and respecting pipeline boundaries. Used as a dependency from workflow skills."
    ),
    user_invocable=False,
    disable_model_invocation=False,
    depends_on=[],
)
