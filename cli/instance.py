"""Manage Claude Code EC2 instances — create, start, stop, status, terminate."""

import json
import sys
from datetime import datetime, timezone

import boto3

from maverick.config import AMI_STATE, INSTANCE_STATE, init_config


def load_instance_state():
    """Load instance state or exit if not found."""
    if not INSTANCE_STATE.exists():
        print("Error: No tracked instance. Run 'maverick instance create' first.")
        sys.exit(1)
    return json.loads(INSTANCE_STATE.read_text())


def save_instance_state(instance_id, state, ip, ami_id, created_at):
    """Write instance state to disk."""
    data = {
        "instance_id": instance_id,
        "ami_id": ami_id,
        "public_ip": ip,
        "state": state,
        "created_at": created_at,
    }
    INSTANCE_STATE.write_text(json.dumps(data, indent=2) + "\n")


def get_aws_state(ec2, instance_id):
    """Query the current instance state from AWS."""
    try:
        resp = ec2.describe_instances(InstanceIds=[instance_id])
        return resp["Reservations"][0]["Instances"][0]["State"]["Name"]
    except Exception:
        return "unknown"


def get_public_ip(ec2, instance_id):
    """Query the current public IP from AWS."""
    try:
        resp = ec2.describe_instances(InstanceIds=[instance_id])
        return resp["Reservations"][0]["Instances"][0].get("PublicIpAddress", "None") or "None"
    except Exception:
        return "None"


def cmd_create(cfg, ec2):
    """Launch a new instance from the baked AMI."""
    if INSTANCE_STATE.exists():
        state = json.loads(INSTANCE_STATE.read_text())
        print(f"Error: An instance is already tracked ({state['instance_id']}).")
        print("Run 'maverick instance terminate' first, or 'maverick instance status' to check it.")
        sys.exit(1)

    if not AMI_STATE.exists():
        print("Error: No AMI found. Run 'maverick build-ami' first.")
        sys.exit(1)

    ami_data = json.loads(AMI_STATE.read_text())
    ami_id = ami_data["ami_id"]

    print(f"==> Creating instance from AMI {ami_id}...")
    run_args = {
        "ImageId": ami_id,
        "InstanceType": cfg["instance"]["type"],
        "KeyName": cfg["aws"]["key_pair"],
        "IamInstanceProfile": {"Name": cfg["aws"]["iam_profile"]},
        "SecurityGroupIds": [cfg["aws"]["security_group"]],
        "TagSpecifications": [
            {
                "ResourceType": "instance",
                "Tags": [{"Key": "Name", "Value": "maverick"}],
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

    print("==> Waiting for instance to be running...")
    ec2.get_waiter("instance_running").wait(InstanceIds=[instance_id])

    ip = get_public_ip(ec2, instance_id)
    created_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    save_instance_state(instance_id, "running", ip, ami_id, created_at)

    print()
    print("=== Instance created ===")
    print(f"  Instance ID: {instance_id}")
    print(f"  Public IP:   {ip}")
    print(f"  SSH:         ssh claude@{ip}")


def cmd_start(cfg, ec2):
    """Start a stopped instance."""
    state = load_instance_state()
    instance_id = state["instance_id"]

    current_state = get_aws_state(ec2, instance_id)
    if current_state != "stopped":
        print(f"Error: Instance {instance_id} is '{current_state}', not 'stopped'.")
        sys.exit(1)

    print(f"==> Starting instance {instance_id}...")
    ec2.start_instances(InstanceIds=[instance_id])
    ec2.get_waiter("instance_running").wait(InstanceIds=[instance_id])

    ip = get_public_ip(ec2, instance_id)
    save_instance_state(instance_id, "running", ip, state["ami_id"], state["created_at"])

    print()
    print("=== Instance started ===")
    print(f"  Instance ID: {instance_id}")
    print(f"  Public IP:   {ip}")
    print(f"  SSH:         ssh claude@{ip}")


def cmd_stop(cfg, ec2):
    """Stop a running instance."""
    state = load_instance_state()
    instance_id = state["instance_id"]

    current_state = get_aws_state(ec2, instance_id)
    if current_state != "running":
        print(f"Error: Instance {instance_id} is '{current_state}', not 'running'.")
        sys.exit(1)

    print(f"==> Stopping instance {instance_id}...")
    ec2.stop_instances(InstanceIds=[instance_id])
    ec2.get_waiter("instance_stopped").wait(InstanceIds=[instance_id])

    save_instance_state(instance_id, "stopped", "None", state["ami_id"], state["created_at"])

    print()
    print("=== Instance stopped ===")
    print(f"  Instance ID: {instance_id}")


def cmd_status(cfg, ec2):
    """Show current instance details."""
    state = load_instance_state()
    instance_id = state["instance_id"]

    current_state = get_aws_state(ec2, instance_id)
    ip = get_public_ip(ec2, instance_id)

    print("=== Instance Status ===")
    print(f"  Instance ID: {instance_id}")
    print(f"  State:       {current_state}")
    print(f"  Public IP:   {ip}")
    print(f"  AMI:         {state['ami_id']}")
    print(f"  Created:     {state['created_at']}")
    print(f"  Region:      {cfg['aws']['region']}")


def cmd_terminate(cfg, ec2):
    """Terminate the instance and remove state."""
    state = load_instance_state()
    instance_id = state["instance_id"]

    confirm = input(f"Terminate instance {instance_id}? This cannot be undone. [y/N] ")
    if confirm.lower() != "y":
        print("Cancelled.")
        sys.exit(0)

    print(f"==> Terminating instance {instance_id}...")
    ec2.terminate_instances(InstanceIds=[instance_id])
    INSTANCE_STATE.unlink()

    print()
    print("=== Instance terminated ===")
    print(f"  Instance {instance_id} has been terminated.")
    print("  State file removed.")


def main(action):
    """Entry point called from cli.py with the subcommand action."""
    cfg = init_config()
    ec2 = boto3.client("ec2", region_name=cfg["aws"]["region"])

    commands = {
        "create": cmd_create,
        "start": cmd_start,
        "stop": cmd_stop,
        "status": cmd_status,
        "terminate": cmd_terminate,
    }
    commands[action](cfg, ec2)
