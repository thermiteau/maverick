from maverick.models import SkillConfig
from maverick.names import MAV_BP_APPLICATION_SECURITY

CONFIG = SkillConfig(
    name=MAV_BP_APPLICATION_SECURITY,
    description=(
        "Application security conventions for all projects. Covers OWASP Top 10 awareness, input validation, secrets management, dependency scanning, SAST/DAST integration, and security headers. Applied when writing or reviewing any code."
    ),
    user_invocable=False,
    disable_model_invocation=False,
    depends_on=[],
)
