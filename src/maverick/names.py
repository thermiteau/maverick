"""Centralised skill and agent name constants for template generators."""

# ---------------------------------------------------------------------------
# Skills
# ---------------------------------------------------------------------------

DO_ISSUE_SOLO = "do-issue-solo"
MAV_BP_ALERTING = "mav-bp-alerting"
MAV_BP_CICD = "mav-bp-cicd"
MAV_BP_CICD_AZURE = "mav-bp-cicd-azure"
MAV_BP_CICD_GITHUB = "mav-bp-cicd-github"
MAV_BP_CICD_GITLAB = "mav-bp-cicd-gitlab"
MAV_BP_INTEGRATION_TESTING = "mav-bp-integration-testing"
MAV_BP_LINTING = "mav-bp-linting"
MAV_BP_LOGGING = "mav-bp-logging"
MAV_BP_UNIT_TESTING = "mav-bp-unit-testing"
MAV_CLAUDE_CODE_RECOVERY = "mav-claude-code-recovery"
MAV_GIT_WORKFLOW = "mav-git-workflow"
MAV_GITHUB_ISSUE_WORKFLOW = "mav-github-issue-workflow"
MAV_LOCAL_VERIFICATION = "mav-local-verification"
MAV_PLAN_EXECUTION = "mav-plan-execution"
MAV_SCOPE_BOUNDARIES = "mav-scope-boundaries"
CREATE_IMPLEMENTATION_PLAN = "create-implementation-plan"
CREATE_SOLUTION_DESIGN = "create-solution-design"
INIT = "init"
INSTALL = "install"
MAV_SYSTEMATIC_DEBUGGING = "mav-systematic-debugging"
MAVERICK_ALIGNMENT = "maverick-alignment"
PULLREQUEST_REVIEW = "pullrequest-review"
TECH_DOCS = "tech-docs"
UPSKILL = "upskill"

ALL_SKILL_NAMES = {
    DO_ISSUE_SOLO,
    MAV_BP_ALERTING,
    MAV_BP_CICD,
    MAV_BP_CICD_AZURE,
    MAV_BP_CICD_GITHUB,
    MAV_BP_CICD_GITLAB,
    MAV_BP_INTEGRATION_TESTING,
    MAV_BP_LINTING,
    MAV_BP_LOGGING,
    MAV_BP_UNIT_TESTING,
    MAV_CLAUDE_CODE_RECOVERY,
    MAV_GIT_WORKFLOW,
    MAV_GITHUB_ISSUE_WORKFLOW,
    MAV_LOCAL_VERIFICATION,
    MAV_PLAN_EXECUTION,
    MAV_SCOPE_BOUNDARIES,
    MAV_SYSTEMATIC_DEBUGGING,
    CREATE_IMPLEMENTATION_PLAN,
    CREATE_SOLUTION_DESIGN,
    INIT,
    INSTALL,
    MAVERICK_ALIGNMENT,
    PULLREQUEST_REVIEW,
    TECH_DOCS,
    UPSKILL,
}

# ---------------------------------------------------------------------------
# Agents
# ---------------------------------------------------------------------------

AGENT_CODE_REVIEWER = "code-reviewer"
AGENT_ISSUE_ANALYST = "issue-analyst"
AGENT_ISSUE_PLANNER = "issue-planner"
AGENT_MAVERICK = "maverick"
AGENT_TECH_DOCS_WRITER = "tech-docs-writer"

ALL_AGENT_NAMES = {
    AGENT_CODE_REVIEWER,
    AGENT_ISSUE_ANALYST,
    AGENT_ISSUE_PLANNER,
    AGENT_MAVERICK,
    AGENT_TECH_DOCS_WRITER,
}
