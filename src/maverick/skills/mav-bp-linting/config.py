from maverick.models import SkillConfig
from maverick.names import MAV_BP_LINTING

CONFIG = SkillConfig(
    name=MAV_BP_LINTING,
    description=(
        "Linting conventions for applications. Covers linter selection, rule configuration, auto-formatting, CI integration, and project linting guidance. Applied when writing or reviewing code, or configuring developer tooling."
    ),
    user_invocable=False,
    disable_model_invocation=False,
    depends_on=[],
)
