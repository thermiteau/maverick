from maverick.models import SkillConfig
from maverick.names import INIT

CONFIG = SkillConfig(
    name=INIT,
    description=(
        "Initialise a project for use with Maverick — creates the .maverick/ directory"
        " and default project config."
    ),
    user_invocable=True,
    disable_model_invocation=True,
)
