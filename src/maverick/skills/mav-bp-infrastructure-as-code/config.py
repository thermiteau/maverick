from maverick.models import SkillConfig
from maverick.names import MAV_BP_INFRASTRUCTURE_AS_CODE

CONFIG = SkillConfig(
    name=MAV_BP_INFRASTRUCTURE_AS_CODE,
    description=(
        "Infrastructure as Code conventions for all deployed projects. Covers IaC principles, environment parity, secrets management in IaC, version control, and runbook fallback for unsupported platforms. Applied when reviewing or configuring infrastructure."
    ),
    user_invocable=False,
    disable_model_invocation=True,
    depends_on=[],
)
