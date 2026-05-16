from maverick.models import SkillConfig
from maverick.names import DO_INSTALL

CONFIG = SkillConfig(
    name=DO_INSTALL,
    description=("Install the maverick CLI tool system-wide from the plugin directory."),
    user_invocable=True,
    disable_model_invocation=False,
)
