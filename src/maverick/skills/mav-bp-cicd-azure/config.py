from maverick.models import SkillConfig
from maverick.names import MAV_BP_CICD_AZURE

CONFIG = SkillConfig(
    name=MAV_BP_CICD_AZURE,
    description=(
        "Monitoring Azure DevOps pipelines after pushing. Covers checking pipeline status, diagnosing build/release failures, and respecting pipeline boundaries. Used as a dependency from workflow skills."
    ),
    user_invocable=False,
    disable_model_invocation=False,
    depends_on=[],
)
