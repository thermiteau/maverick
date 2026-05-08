from maverick.models import SkillConfig
from maverick.names import MAV_BP_DEPENDENCY_MANAGEMENT

CONFIG = SkillConfig(
    name=MAV_BP_DEPENDENCY_MANAGEMENT,
    description=(
        "Dependency management conventions for all projects. Covers lock files, version pinning, vulnerability scanning, license compliance, update strategy, and minimal dependency principle. Applied when adding, updating, or reviewing dependencies."
    ),
    user_invocable=False,
    disable_model_invocation=True,
    depends_on=[],
)
