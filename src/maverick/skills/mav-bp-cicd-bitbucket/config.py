from maverick.models import SkillConfig
from maverick.names import MAV_BP_CICD_BITBUCKET

CONFIG = SkillConfig(
    name=MAV_BP_CICD_BITBUCKET,
    description=(
        "Monitoring Bitbucket Pipelines after pushing. Covers checking pipeline status, diagnosing build failures, and respecting pipeline boundaries. Used as a dependency from workflow skills."
    ),
    user_invocable=False,
    disable_model_invocation=True,
    depends_on=[],
)
