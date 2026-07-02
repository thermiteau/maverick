from maverick.models import SkillConfig
from maverick.names import DO_INSTALL

CONFIG = SkillConfig(
    name=DO_INSTALL,
    description=("Install the maverick CLI tool system-wide from the plugin directory."),
    user_invocable=True,
    # Runs in an isolated forked context: the audit/setup work is
    # self-contained and would otherwise pollute the caller's window
    # (the #106 premature-stop class). The body is the fork's prompt.
    context="fork",
    disable_model_invocation=False,
)
