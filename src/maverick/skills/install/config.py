from maverick.models import SkillConfig
from maverick.names import INSTALL

CONFIG = SkillConfig(
    name=INSTALL,
    description=(
        "Install the maverick CLI tool system-wide from the plugin directory."
    ),
    user_invocable=True,
    disable_model_invocation=False,
)
