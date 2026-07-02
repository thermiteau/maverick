from maverick.models import SkillConfig
from maverick.names import (
    DO_CYBERSECURITY_REVIEW,
    MAV_BP_APPLICATION_SECURITY,
    MAV_SCOPE_BOUNDARIES,
)

CONFIG = SkillConfig(
    name=DO_CYBERSECURITY_REVIEW,
    description=(
        "Audit a codebase for security risks in one of two modes. In full-audit "
        "mode it scans the entire codebase and writes a findings report to "
        "docs/security-audit.md (run as part of do-init or on demand). In update "
        "mode it reviews only a diff plus the code it could impact, returning a "
        "structured findings list as a pre-push gate for do-issue-solo and "
        "do-issue-guided. Covers secrets exposure, dependency vulnerabilities, "
        "authentication and authorisation patterns, input validation, transport "
        "security, and common OWASP risks."
    ),
    user_invocable=True,
    # Runs in an isolated forked context: the audit/setup work is
    # self-contained and would otherwise pollute the caller's window
    # (the #106 premature-stop class). The body is the fork's prompt.
    context="fork",
    disable_model_invocation=False,
    depends_on=[MAV_BP_APPLICATION_SECURITY, MAV_SCOPE_BOUNDARIES],
)
