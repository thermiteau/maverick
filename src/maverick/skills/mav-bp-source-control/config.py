from maverick.models import SkillConfig
from maverick.names import MAV_BP_SOURCE_CONTROL

CONFIG = SkillConfig(
    name=MAV_BP_SOURCE_CONTROL,
    description=(
        "Source control conventions for all projects. Covers the requirement for remote repositories, repository hygiene, .gitignore standards, and sensitive file protection. Applied as a foundational requirement for all projects."
    ),
    user_invocable=False,
    disable_model_invocation=True,
    depends_on=[],
)
