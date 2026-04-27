from maverick.models import SkillConfig
from maverick.names import DO_DOCS, DO_INIT, DO_INSTALL, DO_UPSKILL

CONFIG = SkillConfig(
    name=DO_INIT,
    description=(
        "Initialise a project for use with Maverick — installs the CLI if needed,"
        " writes the project config with integration tracking, scaffolds docs, and"
        " generates project skills."
    ),
    user_invocable=True,
    disable_model_invocation=True,
    depends_on=[DO_INSTALL, DO_DOCS, DO_UPSKILL],
)
