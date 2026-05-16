from maverick.models import SkillConfig
from maverick.names import (
    DO_CYBERSECURITY_REVIEW,
    MAV_BP_APPLICATION_SECURITY,
    MAV_SCOPE_BOUNDARIES,
)

CONFIG = SkillConfig(
    name=DO_CYBERSECURITY_REVIEW,
    description=(
        "Run a security audit of the project's existing codebase and write a "
        "findings report to docs/security-audit.md. Covers secrets exposure, "
        "dependency vulnerabilities, authentication and authorisation patterns, "
        "input validation, transport security, and common OWASP risks. Run as "
        "part of do-init or on demand."
    ),
    user_invocable=True,
    disable_model_invocation=False,
    depends_on=[MAV_BP_APPLICATION_SECURITY, MAV_SCOPE_BOUNDARIES],
)
