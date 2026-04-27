from maverick.models import SkillConfig
from maverick.names import (
    DO_CYBERSECURITY_REVIEW,
    DO_DOCS,
    DO_INIT,
    DO_INSTALL,
    DO_UPSKILL,
)

CONFIG = SkillConfig(
    name=DO_INIT,
    description=(
        "Initialise a project for use with Maverick — installs the CLI if needed,"
        " writes the project config with integration tracking, scaffolds docs,"
        " generates project skills, and runs an initial cybersecurity audit."
    ),
    user_invocable=True,
    disable_model_invocation=True,
    depends_on=[DO_INSTALL, DO_DOCS, DO_UPSKILL, DO_CYBERSECURITY_REVIEW],
)
