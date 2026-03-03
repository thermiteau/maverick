"""Provision and manage AWS infrastructure for the maverick worker pipeline."""

import io
import json
import sys
import zipfile
from pathlib import Path

import boto3
from botocore.exceptions import ClientError

from maverick.config import INFRA_STATE, STATE_DIR, init_config, save_config

LAMBDA_FUNCTION_NAME = "maverick-webhook"
LAMBDA_ROLE_NAME = "maverick-lambda-role"
LAMBDA_POLICY_NAME = "maverick-lambda-policy"
EC2_WORKER_POLICY_NAME = "maverick-ec2-worker-policy"
QUEUE_NAME = "maverick-work"
DLQ_NAME = "maverick-work-dlq"


def _load_infra_state():
    if INFRA_STATE.exists():
        return json.loads(INFRA_STATE.read_text())
    return {}


def _save_infra_state(state):
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    INFRA_STATE.write_text(json.dumps(state, indent=2) + "\n")


def _get_account_id():
    return boto3.client("sts").get_caller_identity()["Account"]


def _ensure_queue(sqs, name, attributes=None):
    """Create or get an SQS queue. Returns queue URL."""
    try:
        resp = sqs.get_queue_url(QueueName=name)
        print(f"    Queue '{name}' already exists.")
        return resp["QueueUrl"]
    except ClientError as e:
        if e.response["Error"]["Code"] != "AWS.SimpleQueueService.NonExistentQueue":
            raise
    print(f"    Creating queue '{name}'...")
    resp = sqs.create_queue(QueueName=name, Attributes=attributes or {})
    return resp["QueueUrl"]


def _ensure_iam_role(iam, role_name, assume_role_policy):
    """Create or get an IAM role. Returns role ARN."""
    try:
        resp = iam.get_role(RoleName=role_name)
        print(f"    Role '{role_name}' already exists.")
        return resp["Role"]["Arn"]
    except ClientError as e:
        if e.response["Error"]["Code"] != "NoSuchEntity":
            raise
    print(f"    Creating role '{role_name}'...")
    resp = iam.create_role(
        RoleName=role_name,
        AssumeRolePolicyDocument=json.dumps(assume_role_policy),
    )
    # Wait for role to propagate
    iam.get_waiter("role_exists").wait(RoleName=role_name)
    return resp["Role"]["Arn"]


def _ensure_iam_policy(iam, policy_name, policy_document, account_id):
    """Create or update an IAM policy. Returns policy ARN."""
    policy_arn = f"arn:aws:iam::{account_id}:policy/{policy_name}"
    try:
        iam.get_policy(PolicyArn=policy_arn)
        print(f"    Policy '{policy_name}' already exists, updating...")
        # Delete oldest non-default version if at limit, then create new
        versions = iam.list_policy_versions(PolicyArn=policy_arn)["Versions"]
        non_default = [v for v in versions if not v["IsDefaultVersion"]]
        if len(non_default) >= 4:
            oldest = sorted(non_default, key=lambda v: v["CreateDate"])[0]
            iam.delete_policy_version(PolicyArn=policy_arn, VersionId=oldest["VersionId"])
        iam.create_policy_version(
            PolicyArn=policy_arn,
            PolicyDocument=json.dumps(policy_document),
            SetAsDefault=True,
        )
        return policy_arn
    except ClientError as e:
        if e.response["Error"]["Code"] != "NoSuchEntity":
            raise
    print(f"    Creating policy '{policy_name}'...")
    resp = iam.create_policy(
        PolicyName=policy_name,
        PolicyDocument=json.dumps(policy_document),
    )
    return resp["Policy"]["Arn"]


def _ensure_role_policy_attachment(iam, role_name, policy_arn):
    """Attach a policy to a role (idempotent)."""
    attached = iam.list_attached_role_policies(RoleName=role_name)["AttachedPolicies"]
    if any(p["PolicyArn"] == policy_arn for p in attached):
        return
    print(f"    Attaching policy to role '{role_name}'...")
    iam.attach_role_policy(RoleName=role_name, PolicyArn=policy_arn)


def _build_lambda_zip():
    """Package lambda_handler.py into an in-memory zip."""
    handler_path = Path(__file__).parent / "lambda_handler.py"
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.write(handler_path, "lambda_handler.py")
    buf.seek(0)
    return buf.read()


def _ensure_lambda(lambda_client, function_name, role_arn, zip_bytes, env_vars):
    """Create or update a Lambda function. Returns function ARN."""
    try:
        resp = lambda_client.get_function(FunctionName=function_name)
        print(f"    Lambda '{function_name}' already exists, updating code...")
        lambda_client.update_function_code(
            FunctionName=function_name,
            ZipFile=zip_bytes,
        )
        lambda_client.get_waiter("function_updated_v2").wait(FunctionName=function_name)
        lambda_client.update_function_configuration(
            FunctionName=function_name,
            Environment={"Variables": env_vars},
            Timeout=30,
            MemorySize=128,
        )
        lambda_client.get_waiter("function_updated_v2").wait(FunctionName=function_name)
        return resp["Configuration"]["FunctionArn"]
    except ClientError as e:
        if e.response["Error"]["Code"] != "ResourceNotFoundException":
            raise
    print(f"    Creating Lambda '{function_name}'...")
    resp = lambda_client.create_function(
        FunctionName=function_name,
        Runtime="python3.12",
        Role=role_arn,
        Handler="lambda_handler.lambda_handler",
        Code={"ZipFile": zip_bytes},
        Environment={"Variables": env_vars},
        Timeout=30,
        MemorySize=128,
    )
    lambda_client.get_waiter("function_active_v2").wait(FunctionName=function_name)
    return resp["FunctionArn"]


def _ensure_function_url(lambda_client, function_name):
    """Create or get a Lambda Function URL. Returns the URL."""
    try:
        resp = lambda_client.get_function_url_config(FunctionName=function_name)
        print(f"    Function URL already exists.")
        return resp["FunctionUrl"]
    except ClientError as e:
        if e.response["Error"]["Code"] != "ResourceNotFoundException":
            raise
    print(f"    Creating Function URL...")
    resp = lambda_client.create_function_url_config(
        FunctionName=function_name,
        AuthType="NONE",
    )
    # Allow public invoke via Function URL
    try:
        lambda_client.add_permission(
            FunctionName=function_name,
            StatementId="FunctionURLAllowPublicAccess",
            Action="lambda:InvokeFunctionUrl",
            Principal="*",
            FunctionUrlAuthType="NONE",
        )
    except ClientError as e:
        if e.response["Error"]["Code"] != "ResourceConflictException":
            raise
    return resp["FunctionUrl"]


def _ensure_log_group(logs, log_group_name):
    """Create a CloudWatch log group if it doesn't exist. Returns the ARN."""
    try:
        resp = logs.describe_log_groups(logGroupNamePrefix=log_group_name)
        for group in resp["logGroups"]:
            if group["logGroupName"] == log_group_name:
                print(f"    Log group '{log_group_name}' already exists.")
                return group["arn"]
    except ClientError:
        pass
    print(f"    Creating log group '{log_group_name}'...")
    logs.create_log_group(logGroupName=log_group_name)
    resp = logs.describe_log_groups(logGroupNamePrefix=log_group_name)
    for group in resp["logGroups"]:
        if group["logGroupName"] == log_group_name:
            return group["arn"]


def _get_role_name_from_profile(iam, profile_name):
    """Get the IAM role name from an instance profile name."""
    resp = iam.get_instance_profile(InstanceProfileName=profile_name)
    roles = resp["InstanceProfile"]["Roles"]
    if not roles:
        print(f"Error: Instance profile '{profile_name}' has no associated role.")
        sys.exit(1)
    return roles[0]["RoleName"]


def deploy():
    """Create or update all infrastructure resources."""
    cfg = init_config()
    region = cfg["aws"]["region"]
    account_id = _get_account_id()

    sqs = boto3.client("sqs", region_name=region)
    iam = boto3.client("iam")
    lambda_client = boto3.client("lambda", region_name=region)
    logs = boto3.client("logs", region_name=region)

    infra = _load_infra_state()
    log_group_name = cfg["worker"]["cloudwatch_log_group"]
    webhook_label = cfg["worker"]["webhook_label"]

    # 1. SQS queues
    print("==> Setting up SQS queues...")
    dlq_url = _ensure_queue(sqs, DLQ_NAME)
    dlq_arn = sqs.get_queue_attributes(
        QueueUrl=dlq_url, AttributeNames=["QueueArn"]
    )["Attributes"]["QueueArn"]

    sqs_cfg = cfg["sqs"]
    queue_url = _ensure_queue(sqs, QUEUE_NAME, attributes={
        "VisibilityTimeout": str(sqs_cfg["visibility_timeout"]),
        "MessageRetentionPeriod": str(sqs_cfg["message_retention"]),
        "RedrivePolicy": json.dumps({
            "deadLetterTargetArn": dlq_arn,
            "maxReceiveCount": str(sqs_cfg["max_receive_count"]),
        }),
    })
    queue_arn = sqs.get_queue_attributes(
        QueueUrl=queue_url, AttributeNames=["QueueArn"]
    )["Attributes"]["QueueArn"]

    # 2. CloudWatch log group
    print("==> Setting up CloudWatch log group...")
    log_group_arn = _ensure_log_group(logs, log_group_name)

    # 3. Lambda IAM role and policy
    print("==> Setting up Lambda IAM role...")
    lambda_assume_policy = {
        "Version": "2012-10-17",
        "Statement": [{
            "Effect": "Allow",
            "Principal": {"Service": "lambda.amazonaws.com"},
            "Action": "sts:AssumeRole",
        }],
    }
    lambda_role_arn = _ensure_iam_role(iam, LAMBDA_ROLE_NAME, lambda_assume_policy)

    lambda_policy_doc = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Action": "sqs:SendMessage",
                "Resource": queue_arn,
            },
            {
                "Effect": "Allow",
                "Action": "secretsmanager:GetSecretValue",
                "Resource": cfg["aws"]["secret_arn"],
            },
            {
                "Effect": "Allow",
                "Action": [
                    "logs:CreateLogGroup",
                    "logs:CreateLogStream",
                    "logs:PutLogEvents",
                ],
                "Resource": "arn:aws:logs:*:*:*",
            },
        ],
    }
    lambda_policy_arn = _ensure_iam_policy(
        iam, LAMBDA_POLICY_NAME, lambda_policy_doc, account_id
    )
    _ensure_role_policy_attachment(iam, LAMBDA_ROLE_NAME, lambda_policy_arn)

    # 4. Lambda function
    print("==> Setting up Lambda function...")
    zip_bytes = _build_lambda_zip()
    env_vars = {
        "SQS_QUEUE_URL": queue_url,
        "SECRET_ARN": cfg["aws"]["secret_arn"],
        "WEBHOOK_LABEL": webhook_label,
    }
    lambda_arn = _ensure_lambda(
        lambda_client, LAMBDA_FUNCTION_NAME, lambda_role_arn, zip_bytes, env_vars
    )

    # 5. Function URL
    function_url = _ensure_function_url(lambda_client, LAMBDA_FUNCTION_NAME)

    # 6. EC2 worker policy
    print("==> Setting up EC2 worker IAM policy...")
    ec2_worker_policy_doc = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Action": [
                    "sqs:ReceiveMessage",
                    "sqs:DeleteMessage",
                    "sqs:GetQueueAttributes",
                ],
                "Resource": queue_arn,
            },
            {
                "Effect": "Allow",
                "Action": [
                    "logs:CreateLogStream",
                    "logs:PutLogEvents",
                ],
                "Resource": f"{log_group_arn}:*",
            },
        ],
    }
    ec2_policy_arn = _ensure_iam_policy(
        iam, EC2_WORKER_POLICY_NAME, ec2_worker_policy_doc, account_id
    )

    # Attach to the existing EC2 instance profile's role
    ec2_role_name = _get_role_name_from_profile(iam, cfg["aws"]["iam_profile"])
    _ensure_role_policy_attachment(iam, ec2_role_name, ec2_policy_arn)

    # 7. Save infra state
    infra = {
        "queue_url": queue_url,
        "queue_arn": queue_arn,
        "dlq_url": dlq_url,
        "dlq_arn": dlq_arn,
        "lambda_arn": lambda_arn,
        "lambda_role_arn": lambda_role_arn,
        "lambda_policy_arn": lambda_policy_arn,
        "function_url": function_url,
        "ec2_policy_arn": ec2_policy_arn,
        "log_group_name": log_group_name,
        "log_group_arn": log_group_arn,
    }
    _save_infra_state(infra)

    # 8. Update config with runtime values
    cfg["aws"]["sqs_queue_url"] = queue_url
    save_config(cfg)

    print()
    print("=== Infrastructure deployed ===")
    print(f"  SQS Queue:      {queue_url}")
    print(f"  DLQ:            {dlq_url}")
    print(f"  Lambda:         {lambda_arn}")
    print(f"  Function URL:   {function_url}")
    print(f"  Log Group:      {log_group_name}")
    print(f"  State saved:    {INFRA_STATE}")
    print()
    print(f"Next: Configure this Function URL as a GitHub webhook")
    print(f"  URL:    {function_url}")
    print(f"  Events: Issues")
    print(f"  Secret: Set GITHUB_WEBHOOK_SECRET in your Secrets Manager secret")


def status():
    """Show current infrastructure resource status."""
    infra = _load_infra_state()
    if not infra:
        print("No infrastructure deployed. Run 'maverick infra deploy' first.")
        sys.exit(1)

    print("=== Infrastructure Status ===")
    print(f"  SQS Queue:    {infra.get('queue_url', 'N/A')}")
    print(f"  DLQ:          {infra.get('dlq_url', 'N/A')}")
    print(f"  Lambda:       {infra.get('lambda_arn', 'N/A')}")
    print(f"  Function URL: {infra.get('function_url', 'N/A')}")
    print(f"  Log Group:    {infra.get('log_group_name', 'N/A')}")
    print(f"  State file:   {INFRA_STATE}")


def destroy():
    """Tear down all infrastructure resources."""
    infra = _load_infra_state()
    if not infra:
        print("No infrastructure to destroy.")
        return

    cfg = init_config()
    region = cfg["aws"]["region"]

    confirm = input("Destroy all maverick infrastructure? This cannot be undone. [y/N] ")
    if confirm.lower() != "y":
        print("Cancelled.")
        return

    sqs = boto3.client("sqs", region_name=region)
    iam = boto3.client("iam")
    lambda_client = boto3.client("lambda", region_name=region)
    logs = boto3.client("logs", region_name=region)

    # Delete Lambda Function URL and Function
    print("==> Deleting Lambda...")
    try:
        lambda_client.delete_function_url_config(FunctionName=LAMBDA_FUNCTION_NAME)
    except ClientError:
        pass
    try:
        lambda_client.delete_function(FunctionName=LAMBDA_FUNCTION_NAME)
    except ClientError:
        pass

    # Detach and delete Lambda policy
    print("==> Cleaning up Lambda IAM...")
    try:
        iam.detach_role_policy(
            RoleName=LAMBDA_ROLE_NAME,
            PolicyArn=infra.get("lambda_policy_arn", ""),
        )
    except ClientError:
        pass
    try:
        # Delete all policy versions before deleting policy
        if infra.get("lambda_policy_arn"):
            versions = iam.list_policy_versions(
                PolicyArn=infra["lambda_policy_arn"]
            )["Versions"]
            for v in versions:
                if not v["IsDefaultVersion"]:
                    iam.delete_policy_version(
                        PolicyArn=infra["lambda_policy_arn"],
                        VersionId=v["VersionId"],
                    )
            iam.delete_policy(PolicyArn=infra["lambda_policy_arn"])
    except ClientError:
        pass
    try:
        iam.delete_role(RoleName=LAMBDA_ROLE_NAME)
    except ClientError:
        pass

    # Detach and delete EC2 worker policy
    print("==> Cleaning up EC2 worker IAM...")
    try:
        ec2_role_name = _get_role_name_from_profile(iam, cfg["aws"]["iam_profile"])
        iam.detach_role_policy(
            RoleName=ec2_role_name,
            PolicyArn=infra.get("ec2_policy_arn", ""),
        )
    except (ClientError, SystemExit):
        pass
    try:
        if infra.get("ec2_policy_arn"):
            versions = iam.list_policy_versions(
                PolicyArn=infra["ec2_policy_arn"]
            )["Versions"]
            for v in versions:
                if not v["IsDefaultVersion"]:
                    iam.delete_policy_version(
                        PolicyArn=infra["ec2_policy_arn"],
                        VersionId=v["VersionId"],
                    )
            iam.delete_policy(PolicyArn=infra["ec2_policy_arn"])
    except ClientError:
        pass

    # Delete SQS queues
    print("==> Deleting SQS queues...")
    try:
        sqs.delete_queue(QueueUrl=infra.get("queue_url", ""))
    except ClientError:
        pass
    try:
        sqs.delete_queue(QueueUrl=infra.get("dlq_url", ""))
    except ClientError:
        pass

    # Delete CloudWatch log group
    print("==> Deleting CloudWatch log group...")
    try:
        logs.delete_log_group(logGroupName=infra.get("log_group_name", ""))
    except ClientError:
        pass

    # Remove state
    INFRA_STATE.unlink(missing_ok=True)

    # Remove runtime config values
    cfg["aws"].pop("sqs_queue_url", None)
    save_config(cfg)

    print()
    print("=== Infrastructure destroyed ===")
