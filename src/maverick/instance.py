"""Manage Claude Code EC2 worker instances — start, stop, status.

The instance lifecycle (create/terminate) is managed by CloudFormation
via 'maverick infra deploy/destroy'. This module handles runtime
operations on the CFN-managed instance.
"""

import sys

import boto3
from botocore.exceptions import ClientError

from maverick.config import init_config
from maverick.infra import STACK_NAME


def _get_instance_id(cfn):
    """Get the worker instance ID from the CloudFormation stack outputs."""
    try:
        resp = cfn.describe_stacks(StackName=STACK_NAME)
        for o in resp["Stacks"][0].get("Outputs", []):
            if o["OutputKey"] == "InstanceId":
                return o["OutputValue"]
    except ClientError as e:
        if "does not exist" not in str(e):
            raise
    print("Error: No worker instance found. Run 'maverick infra deploy' first.")
    sys.exit(1)


def _get_instance_info(ec2, instance_id):
    """Query instance state and public IP from AWS."""
    try:
        resp = ec2.describe_instances(InstanceIds=[instance_id])
        inst = resp["Reservations"][0]["Instances"][0]
        return inst["State"]["Name"], inst.get("PublicIpAddress") or "None"
    except Exception:
        return "unknown", "None"


def cmd_start(ec2, cfn):
    """Start a stopped instance."""
    instance_id = _get_instance_id(cfn)
    state, _ = _get_instance_info(ec2, instance_id)
    if state != "stopped":
        print(f"Error: Instance {instance_id} is '{state}', not 'stopped'.")
        sys.exit(1)

    print(f"==> Starting instance {instance_id}...")
    ec2.start_instances(InstanceIds=[instance_id])
    ec2.get_waiter("instance_running").wait(InstanceIds=[instance_id])

    _, ip = _get_instance_info(ec2, instance_id)
    print()
    print("=== Instance started ===")
    print(f"  Instance ID: {instance_id}")
    print(f"  Public IP:   {ip}")
    print(f"  SSH:         ssh claude@{ip}")


def cmd_stop(ec2, cfn):
    """Stop a running instance."""
    instance_id = _get_instance_id(cfn)
    state, _ = _get_instance_info(ec2, instance_id)
    if state != "running":
        print(f"Error: Instance {instance_id} is '{state}', not 'running'.")
        sys.exit(1)

    print(f"==> Stopping instance {instance_id}...")
    ec2.stop_instances(InstanceIds=[instance_id])
    ec2.get_waiter("instance_stopped").wait(InstanceIds=[instance_id])

    print()
    print("=== Instance stopped ===")
    print(f"  Instance ID: {instance_id}")


def cmd_status(ec2, cfn):
    """Show current instance details."""
    instance_id = _get_instance_id(cfn)
    state, ip = _get_instance_info(ec2, instance_id)
    cfg = init_config()

    print("=== Instance Status ===")
    print(f"  Instance ID: {instance_id}")
    print(f"  State:       {state}")
    print(f"  Public IP:   {ip}")
    print(f"  Region:      {cfg['aws']['region']}")
    if state == "running" and ip != "None":
        print(f"  SSH:         ssh claude@{ip}")


def main(action):
    """Entry point called from cli.py with the subcommand action."""
    cfg = init_config()
    region = cfg["aws"]["region"]
    ec2 = boto3.client("ec2", region_name=region)
    cfn = boto3.client("cloudformation", region_name=region)

    commands = {
        "start": cmd_start,
        "stop": cmd_stop,
        "status": cmd_status,
    }
    commands[action](ec2, cfn)
