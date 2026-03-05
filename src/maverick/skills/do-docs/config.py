from maverick.models import SkillConfig
from maverick.names import DO_DOCS, MAV_SCOPE_BOUNDARIES, TECH_DOCS

CONFIG = SkillConfig(
    name=DO_DOCS,
    description=(
        "Create, restructure, or update technical documentation."
        " Handles greenfield projects, refactoring non-compliant docs,"
        " and incremental updates after code changes."
    ),
    argument_hint="mode: greenfield, refactor, or update (auto-detected if omitted)",
    user_invocable=True,
    disable_model_invocation=False,
    depends_on=[TECH_DOCS, MAV_SCOPE_BOUNDARIES],
)
