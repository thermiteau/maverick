"""Build a Claude Code AMI from Ubuntu 24.04 LTS with cloud-init provisioning."""

import json
import sys
from datetime import datetime, timezone
from importlib import resources
from pathlib import Path

import boto3

from maverick.config import AMI_STATE, CONFIG_FILE, init_config

BUNDLED_CLOUD_CONFIG = "cloud-config.yaml"


def _get_cloud_config_path(cfg):
    """Resolve cloud config path: use config override if set, otherwise bundled package data."""
    config_value = cfg["aws"].get("cloud_config", "")
    if config_value:
        explicit = Path(config_value).resolve()
        if explicit.exists():
            return explicit

    # Fall back to bundled package data
    bundled = Path(str(resources.files("maverick.cloud_init"))) / BUNDLED_CLOUD_CONFIG
    if bundled.exists():
        return bundled

    print("Error: Cloud config not found.")
    if config_value:
        print(f"  Checked: {Path(config_value).resolve()}")
    print(f"  Checked: bundled package data")
    sys.exit(1)


def validate_config(cfg):
    """Check that required AWS fields are non-empty."""
    required = {
        "secret_arn": cfg["aws"].get("secret_arn", ""),
        "iam_profile": cfg["aws"].get("iam_profile", ""),
        "key_pair": cfg["aws"].get("key_pair", ""),
        "security_group": cfg["aws"].get("security_group", ""),
    }
    missing = [name for name, value in required.items() if not value]

    if missing:
        print("Error: The following config values are empty:")
        for name in missing:
            print(f"  - aws.{name}")
        print(f"Edit {CONFIG_FILE} and try again.")
        sys.exit(1)

    return _get_cloud_config_path(cfg)


def main():
    cfg = init_config()
    cloud_config_path = validate_config(cfg)
    region = cfg["aws"]["region"]

    ssm = boto3.client("ssm", region_name=region)
    ec2 = boto3.client("ec2", region_name=region)

    # Look up Ubuntu 24.04 LTS AMI
    ssm_parameter = cfg["ami"]["ssm_parameter"]
    print(f"==> Looking up latest Ubuntu 24.04 LTS AMI in {region}...")
    resp = ssm.get_parameters(Names=[ssm_parameter])
    source_ami = resp["Parameters"][0]["Value"]
    print(f"    Base AMI: {source_ami}")

    # Launch build instance
    print("==> Launching build instance...")
    user_data = cloud_config_path.read_text()
    run_args = {
        "ImageId": source_ami,
        "InstanceType": cfg["instance"]["type"],
        "KeyName": cfg["aws"]["key_pair"],
        "IamInstanceProfile": {"Name": cfg["aws"]["iam_profile"]},
        "SecurityGroupIds": [cfg["aws"]["security_group"]],
        "UserData": user_data,
        "TagSpecifications": [
            {
                "ResourceType": "instance",
                "Tags": [{"Key": "Name", "Value": "maverick-build"}],
            }
        ],
        "MinCount": 1,
        "MaxCount": 1,
    }
    subnet = cfg["aws"].get("subnet", "")
    if subnet:
        run_args["SubnetId"] = subnet

    instance_id = ec2.run_instances(**run_args)["Instances"][0]["InstanceId"]
    print(f"    Instance: {instance_id}")
    print(
        f"    (If this script fails, clean up with: "
        f"aws ec2 terminate-instances --instance-ids {instance_id} --region {region})"
    )

    # Wait for status checks
    print("==> Waiting for instance status checks to pass (this may take 10-15 minutes)...")
    ec2.get_waiter("instance_status_ok").wait(InstanceIds=[instance_id])
    print("    Status checks passed.")

    # Stop instance
    print("==> Stopping instance...")
    ec2.stop_instances(InstanceIds=[instance_id])
    ec2.get_waiter("instance_stopped").wait(InstanceIds=[instance_id])
    print("    Instance stopped.")

    # Create AMI
    ami_name = f"maverick-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}"
    ami_description = cfg["ami"]["description"]
    print(f"==> Creating AMI: {ami_name}...")
    ami_id = ec2.create_image(
        InstanceId=instance_id,
        Name=ami_name,
        Description=ami_description,
    )["ImageId"]
    print(f"    AMI: {ami_id}")

    # Wait for AMI
    print("==> Waiting for AMI to become available...")
    ec2.get_waiter("image_available").wait(ImageIds=[ami_id])
    print("    AMI ready.")

    # Terminate build instance
    print("==> Terminating build instance...")
    ec2.terminate_instances(InstanceIds=[instance_id])
    print("    Build instance terminated.")

    # Write AMI state
    ami_state = {
        "ami_id": ami_id,
        "created_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source_ami": source_ami,
    }
    AMI_STATE.write_text(json.dumps(ami_state, indent=2) + "\n")

    print()
    print("=== Build complete ===")
    print(f"  AMI ID:      {ami_id}")
    print(f"  Region:      {region}")
    print(f"  State saved: {AMI_STATE}")
    print()
    print("Next: maverick instance create")
