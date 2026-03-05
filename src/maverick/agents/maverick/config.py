from maverick.models import AgentConfig
from maverick.names import AGENT_MAVERICK, INIT, INSTALL

CONFIG = AgentConfig(
    name=AGENT_MAVERICK,
    description=(
        "Handles Maverick plugin and CLI management — installation, project"
        " initialisation, and configuration. Dispatched so that CLI internals don't"
        " consume the caller's context."
    ),
    color="magenta",
    skills=[
        INIT,
        INSTALL,
    ],
)
