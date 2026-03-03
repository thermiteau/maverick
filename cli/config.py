"""Shared state and configuration for maverick CLI."""

import sys
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib

STATE_DIR = Path.home() / ".maverick"
CONFIG_FILE = STATE_DIR / "config.toml"
AMI_STATE = STATE_DIR / "ami.json"
INSTANCE_STATE = STATE_DIR / "instance.json"
INFRA_STATE = STATE_DIR / "infra.json"

STARTER_CONFIG = """\
# maverick configuration
# Fill in your AWS values, then re-run the command.

[aws]
region = ""
secret_arn = ""
iam_profile = ""
key_pair = ""
security_group = ""
subnet = ""
# sqs_queue_url is set automatically by 'maverick infra deploy'
# sqs_queue_url = ""

[ami]
ssm_parameter = "/aws/service/canonical/ubuntu/server/24.04/stable/current/amd64/hvm/ebs-gp3/ami-id"
description = "Claude Code pre-configured instance"

[instance]
type = "t3.medium"

[worker]
webhook_label = "claude-do"
cloudwatch_log_group = "/maverick/worker"
prompt_template = "Complete GitHub issue #{issue_number} following the do-issue-solo skill"
work_dir = "/tmp/maverick-work"
user = "claude"

[sqs]
visibility_timeout = 3600
message_retention = 345600
max_receive_count = 3
"""

# Old JSON config path for migration detection
_OLD_CONFIG_FILE = STATE_DIR / "config.json"


def init_config():
    """Load config, creating a starter file if none exists."""
    STATE_DIR.mkdir(parents=True, exist_ok=True)

    # Migration notice
    if _OLD_CONFIG_FILE.exists() and not CONFIG_FILE.exists():
        print(f"Note: config format has changed from JSON to TOML.")
        print(f"A new starter config has been created at {CONFIG_FILE}")
        print(f"Your old config.json is preserved — please copy your values across.")
        CONFIG_FILE.write_text(STARTER_CONFIG)
        sys.exit(1)

    if not CONFIG_FILE.exists():
        CONFIG_FILE.write_text(STARTER_CONFIG)
        print(f"Created starter config at {CONFIG_FILE}")
        print("Please edit it with your AWS values, then re-run.")
        sys.exit(1)

    return tomllib.loads(CONFIG_FILE.read_text())


def save_config(cfg):
    """Write config back to TOML file.

    Uses a simple serialiser that preserves the section/key structure.
    Only handles the flat-section layout used by maverick config.
    """
    lines = []
    for section, values in cfg.items():
        if not isinstance(values, dict):
            continue
        lines.append(f"[{section}]")
        for key, value in values.items():
            if isinstance(value, str):
                lines.append(f'{key} = "{value}"')
            elif isinstance(value, bool):
                lines.append(f"{key} = {'true' if value else 'false'}")
            elif isinstance(value, int):
                lines.append(f"{key} = {value}")
            elif isinstance(value, float):
                lines.append(f"{key} = {value}")
        lines.append("")
    CONFIG_FILE.write_text("\n".join(lines) + "\n")
