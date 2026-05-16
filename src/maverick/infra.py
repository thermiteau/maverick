"""Provision and manage AWS infrastructure for the maverick worker pipeline.

Uses CloudFormation stacks instead of imperative boto3 calls.
Two stacks:
  - maverick-vpc   — VPC, subnet, IGW, route table, security group, IAM profile, secret
                     (preserved on destroy by default)
  - maverick-infra — DynamoDB, Lambda, IAM, CloudWatch log group, EC2 worker instance
"""

import json
import sys
import time
from pathlib import Path

import boto3
from botocore.exceptions import ClientError, NoCredentialsError, PartialCredentialsError

from maverick.config import (
    AMI_STATE,
    INFRA_STATE,
    INSTANCE_STATE,
    init_config,
    save_config,
)

STACK_NAME = "maverick-infra"
VPC_STACK_NAME = "maverick-vpc"

VPC_NAME = "maverick-workers"
VPC_CIDR = "10.0.0.0/16"
SUBNET_CIDR = "10.0.1.0/24"


class InfraError(Exception):
    """Raised when an infrastructure operation fails."""


# ---------------------------------------------------------------------------
# AWS helpers
# ---------------------------------------------------------------------------


def _get_account_id():
    try:
        return boto3.client("sts").get_caller_identity()["Account"]
    except (NoCredentialsError, PartialCredentialsError) as e:
        raise InfraError(
            "AWS credentials not found. Configure credentials via:\n"
            "  - Environment variables (AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY)\n"
            "  - AWS CLI profile (aws configure)\n"
            "  - IAM instance role (if running on EC2)"
        ) from e
    except ClientError as e:
        raise InfraError(f"Failed to verify AWS identity: {e.response['Error']['Message']}") from e


def _get_role_name_from_profile(iam, profile_name):
    """Get the IAM role name from an instance profile name."""
    try:
        resp = iam.get_instance_profile(InstanceProfileName=profile_name)
    except ClientError as e:
        raise InfraError(
            f"Instance profile '{profile_name}' not found: {e.response['Error']['Message']}"
        ) from e
    roles = resp["InstanceProfile"]["Roles"]
    if not roles:
        raise InfraError(f"Instance profile '{profile_name}' has no associated IAM role.")
    return roles[0]["RoleName"]


def _ensure_role_policy_attachment(iam, role_name, policy_arn):
    """Attach a policy to a role (idempotent)."""
    attached = iam.list_attached_role_policies(RoleName=role_name)["AttachedPolicies"]
    if any(p["PolicyArn"] == policy_arn for p in attached):
        return
    print(f"    Attaching policy to role '{role_name}'...")
    iam.attach_role_policy(RoleName=role_name, PolicyArn=policy_arn)


def _resolve_ami(region, cfg):
    """Resolve AMI ID: prefer maverick-baked AMI, fall back to Ubuntu 24.04 LTS."""
    ec2 = boto3.client("ec2", region_name=region)

    # 1. Check for a maverick-baked AMI
    if AMI_STATE.exists():
        ami_data = json.loads(AMI_STATE.read_text())
        ami_id = ami_data.get("ami_id")
        if ami_id:
            try:
                resp = ec2.describe_images(ImageIds=[ami_id])
                if resp["Images"] and resp["Images"][0]["State"] == "available":
                    print(f"    Using maverick AMI: {ami_id}")
                    return ami_id
            except ClientError:
                pass
            print(f"    Maverick AMI {ami_id} not available, falling back to Ubuntu LTS.")

    # 2. Fall back to Ubuntu 24.04 LTS via SSM
    ssm = boto3.client("ssm", region_name=region)
    ssm_param = cfg["ami"]["ssm_parameter"]
    try:
        resp = ssm.get_parameters(Names=[ssm_param])
        if resp["Parameters"]:
            ami_id = resp["Parameters"][0]["Value"]
            print(f"    Using Ubuntu 24.04 LTS AMI: {ami_id}")
            return ami_id
    except ClientError as e:
        raise InfraError(f"Failed to look up Ubuntu LTS AMI: {e.response['Error']['Message']}") from e

    raise InfraError(
        "Could not resolve AMI: no maverick AMI found and Ubuntu LTS SSM lookup failed."
    )


def _prepare_user_data():
    """Read bundled cloud-config and prepare for CloudFormation Fn::Sub embedding.

    Replaces placeholder values with CFN variable references so that
    Fn::Sub injects the real SecretArn and region at stack creation time.
    Shell $VAR references are bare (not ${VAR}), so Fn::Sub leaves them alone.
    """
    cloud_config_path = Path(__file__).parent / "cloud_init" / "cloud-config.yaml"
    raw = cloud_config_path.read_text()
    text = raw.replace(
        "arn:aws:secretsmanager:us-east-1:123456789:secret:claude-vps/api-keys",
        "${SecretArn}",
    )
    text = text.replace("--region us-east-1", "--region ${AWS::Region}")
    return text


# ---------------------------------------------------------------------------
# CloudFormation templates
# ---------------------------------------------------------------------------


def _build_vpc_template():
    """Return a CloudFormation template dict for the VPC stack."""
    return {
        "AWSTemplateFormatVersion": "2010-09-09",
        "Description": "Maverick worker VPC - managed by maverick CLI",
        "Parameters": {
            "SshCidr": {
                "Type": "String",
                "Default": "0.0.0.0/0",
                "Description": "CIDR block allowed SSH access to the worker instance",
            },
        },
        "Resources": {
            "Vpc": {
                "Type": "AWS::EC2::VPC",
                "Properties": {
                    "CidrBlock": VPC_CIDR,
                    "EnableDnsSupport": True,
                    "EnableDnsHostnames": True,
                    "Tags": [{"Key": "Name", "Value": VPC_NAME}],
                },
            },
            "InternetGateway": {
                "Type": "AWS::EC2::InternetGateway",
                "Properties": {
                    "Tags": [{"Key": "Name", "Value": f"{VPC_NAME}-igw"}],
                },
            },
            "VpcGatewayAttachment": {
                "Type": "AWS::EC2::VPCGatewayAttachment",
                "Properties": {
                    "VpcId": {"Ref": "Vpc"},
                    "InternetGatewayId": {"Ref": "InternetGateway"},
                },
            },
            "PublicSubnet": {
                "Type": "AWS::EC2::Subnet",
                "Properties": {
                    "VpcId": {"Ref": "Vpc"},
                    "CidrBlock": SUBNET_CIDR,
                    "AvailabilityZone": {
                        "Fn::Select": ["0", {"Fn::GetAZs": {"Ref": "AWS::Region"}}],
                    },
                    "MapPublicIpOnLaunch": True,
                    "Tags": [{"Key": "Name", "Value": f"{VPC_NAME}-public"}],
                },
            },
            "RouteTable": {
                "Type": "AWS::EC2::RouteTable",
                "Properties": {
                    "VpcId": {"Ref": "Vpc"},
                    "Tags": [{"Key": "Name", "Value": f"{VPC_NAME}-rt"}],
                },
            },
            "DefaultRoute": {
                "Type": "AWS::EC2::Route",
                "DependsOn": "VpcGatewayAttachment",
                "Properties": {
                    "RouteTableId": {"Ref": "RouteTable"},
                    "DestinationCidrBlock": "0.0.0.0/0",
                    "GatewayId": {"Ref": "InternetGateway"},
                },
            },
            "SubnetRouteTableAssociation": {
                "Type": "AWS::EC2::SubnetRouteTableAssociation",
                "Properties": {
                    "SubnetId": {"Ref": "PublicSubnet"},
                    "RouteTableId": {"Ref": "RouteTable"},
                },
            },
            "WorkerSecurityGroup": {
                "Type": "AWS::EC2::SecurityGroup",
                "Properties": {
                    "GroupDescription": "Maverick worker instance - SSH inbound, all outbound",
                    "VpcId": {"Ref": "Vpc"},
                    "SecurityGroupIngress": [
                        {
                            "IpProtocol": "tcp",
                            "FromPort": 22,
                            "ToPort": 22,
                            "CidrIp": {"Ref": "SshCidr"},
                        },
                    ],
                    "SecurityGroupEgress": [
                        {
                            "IpProtocol": "-1",
                            "CidrIp": "0.0.0.0/0",
                        },
                    ],
                    "Tags": [{"Key": "Name", "Value": f"{VPC_NAME}-worker-sg"}],
                },
            },
            "WorkerSecret": {
                "Type": "AWS::SecretsManager::Secret",
                "Properties": {
                    "Description": "Maverick worker secrets (API keys, webhook secret)",
                    "SecretString": json.dumps({
                        "GITHUB_WEBHOOK_SECRET": "CHANGE_ME",
                        "ANTHROPIC_API_KEY": "CHANGE_ME",
                        "GITHUB_PERSONAL_ACCESS_TOKEN": "CHANGE_ME",
                    }),
                },
            },
            "WorkerRole": {
                "Type": "AWS::IAM::Role",
                "Properties": {
                    "RoleName": "maverick-worker-role",
                    "AssumeRolePolicyDocument": {
                        "Version": "2012-10-17",
                        "Statement": [
                            {
                                "Effect": "Allow",
                                "Principal": {"Service": "ec2.amazonaws.com"},
                                "Action": "sts:AssumeRole",
                            },
                        ],
                    },
                    "Policies": [
                        {
                            "PolicyName": "maverick-worker-secret-access",
                            "PolicyDocument": {
                                "Version": "2012-10-17",
                                "Statement": [
                                    {
                                        "Effect": "Allow",
                                        "Action": "secretsmanager:GetSecretValue",
                                        "Resource": {"Ref": "WorkerSecret"},
                                    },
                                ],
                            },
                        },
                    ],
                },
            },
            "WorkerInstanceProfile": {
                "Type": "AWS::IAM::InstanceProfile",
                "Properties": {
                    "InstanceProfileName": "maverick-worker-profile",
                    "Roles": [{"Ref": "WorkerRole"}],
                },
            },
        },
        "Outputs": {
            "VpcId": {
                "Value": {"Ref": "Vpc"},
                "Description": "VPC ID",
            },
            "SubnetId": {
                "Value": {"Ref": "PublicSubnet"},
                "Description": "Public subnet ID",
            },
            "SecurityGroupId": {
                "Value": {"Ref": "WorkerSecurityGroup"},
                "Description": "Worker security group ID",
            },
            "InstanceProfileName": {
                "Value": {"Ref": "WorkerInstanceProfile"},
                "Description": "IAM instance profile name for the worker",
            },
            "RoleName": {
                "Value": {"Ref": "WorkerRole"},
                "Description": "IAM role name for the worker",
            },
            "SecretArn": {
                "Value": {"Ref": "WorkerSecret"},
                "Description": "Secrets Manager secret ARN",
            },
        },
    }


def _build_infra_template(lambda_code, user_data):
    """Return a CloudFormation template dict for the main infrastructure stack."""
    return {
        "AWSTemplateFormatVersion": "2010-09-09",
        "Description": "Maverick worker infrastructure — managed by maverick CLI",
        "Parameters": {
            "SecretArn": {
                "Type": "String",
                "Description": "ARN of the Secrets Manager secret (webhook + instance secrets)",
            },
            "WebhookLabel": {
                "Type": "String",
                "Default": "claude-do",
                "Description": "GitHub label that triggers work items",
            },
            "LogGroupName": {
                "Type": "String",
                "Default": "/maverick/worker",
                "Description": "CloudWatch log group name for workers",
            },
            "VpcSubnetId": {
                "Type": "AWS::EC2::Subnet::Id",
                "Description": "Subnet ID from the VPC stack",
            },
            "AmiId": {
                "Type": "AWS::EC2::Image::Id",
                "Description": "AMI ID — use a maverick-baked AMI or Ubuntu 24.04 LTS",
            },
            "InstanceType": {
                "Type": "String",
                "Default": "t3.medium",
                "Description": "EC2 instance type for the worker",
            },
            "KeyPairName": {
                "Type": "AWS::EC2::KeyPair::KeyName",
                "Description": "EC2 key pair for SSH access",
            },
            "SecurityGroupId": {
                "Type": "AWS::EC2::SecurityGroup::Id",
                "Description": "Security group ID for the worker instance",
            },
            "IamInstanceProfileName": {
                "Type": "String",
                "Description": "IAM instance profile name for the worker instance",
            },
        },
        "Resources": {
            "WorkTable": {
                "Type": "AWS::DynamoDB::Table",
                "Properties": {
                    "TableName": "maverick-work",
                    "BillingMode": "PAY_PER_REQUEST",
                    "KeySchema": [
                        {"AttributeName": "id", "KeyType": "HASH"},
                    ],
                    "AttributeDefinitions": [
                        {"AttributeName": "id", "AttributeType": "S"},
                        {"AttributeName": "status", "AttributeType": "S"},
                        {"AttributeName": "created_at", "AttributeType": "S"},
                    ],
                    "GlobalSecondaryIndexes": [
                        {
                            "IndexName": "status-created_at-index",
                            "KeySchema": [
                                {"AttributeName": "status", "KeyType": "HASH"},
                                {"AttributeName": "created_at", "KeyType": "RANGE"},
                            ],
                            "Projection": {"ProjectionType": "ALL"},
                        },
                    ],
                    "TimeToLiveSpecification": {
                        "AttributeName": "ttl_expiry",
                        "Enabled": True,
                    },
                },
            },
            "WorkerLogGroup": {
                "Type": "AWS::Logs::LogGroup",
                "Properties": {
                    "LogGroupName": {"Ref": "LogGroupName"},
                },
            },
            "LambdaRole": {
                "Type": "AWS::IAM::Role",
                "Properties": {
                    "RoleName": "maverick-webhook-role",
                    "AssumeRolePolicyDocument": {
                        "Version": "2012-10-17",
                        "Statement": [
                            {
                                "Effect": "Allow",
                                "Principal": {"Service": "lambda.amazonaws.com"},
                                "Action": "sts:AssumeRole",
                            },
                        ],
                    },
                    "Policies": [
                        {
                            "PolicyName": "maverick-webhook-policy",
                            "PolicyDocument": {
                                "Version": "2012-10-17",
                                "Statement": [
                                    {
                                        "Effect": "Allow",
                                        "Action": "dynamodb:PutItem",
                                        "Resource": {"Fn::GetAtt": ["WorkTable", "Arn"]},
                                    },
                                    {
                                        "Effect": "Allow",
                                        "Action": "secretsmanager:GetSecretValue",
                                        "Resource": {"Ref": "SecretArn"},
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
                            },
                        },
                    ],
                },
            },
            "WebhookFunction": {
                "Type": "AWS::Lambda::Function",
                "Properties": {
                    "FunctionName": "maverick-webhook",
                    "Runtime": "python3.12",
                    "Handler": "index.lambda_handler",
                    "Timeout": 30,
                    "MemorySize": 128,
                    "Role": {"Fn::GetAtt": ["LambdaRole", "Arn"]},
                    "Code": {
                        "ZipFile": lambda_code,
                    },
                    "Environment": {
                        "Variables": {
                            "WORK_TABLE_NAME": {"Ref": "WorkTable"},
                            "SECRET_ARN": {"Ref": "SecretArn"},
                            "WEBHOOK_LABEL": {"Ref": "WebhookLabel"},
                        },
                    },
                },
            },
            "WebhookFunctionUrl": {
                "Type": "AWS::Lambda::Url",
                "Properties": {
                    "TargetFunctionArn": {"Ref": "WebhookFunction"},
                    "AuthType": "NONE",
                },
            },
            "WebhookFunctionUrlPermission": {
                "Type": "AWS::Lambda::Permission",
                "Properties": {
                    "FunctionName": {"Ref": "WebhookFunction"},
                    "Action": "lambda:InvokeFunctionUrl",
                    "Principal": "*",
                    "FunctionUrlAuthType": "NONE",
                },
            },
            "WorkerPolicy": {
                "Type": "AWS::IAM::ManagedPolicy",
                "Properties": {
                    "ManagedPolicyName": "maverick-worker-policy",
                    "PolicyDocument": {
                        "Version": "2012-10-17",
                        "Statement": [
                            {
                                "Effect": "Allow",
                                "Action": [
                                    "dynamodb:Query",
                                    "dynamodb:UpdateItem",
                                    "dynamodb:GetItem",
                                ],
                                "Resource": [
                                    {"Fn::GetAtt": ["WorkTable", "Arn"]},
                                    {"Fn::Sub": "${WorkTable.Arn}/index/*"},
                                ],
                            },
                            {
                                "Effect": "Allow",
                                "Action": [
                                    "logs:CreateLogStream",
                                    "logs:PutLogEvents",
                                ],
                                "Resource": {"Fn::Sub": "${WorkerLogGroup.Arn}:*"},
                            },
                        ],
                    },
                },
            },
            "WorkerInstance": {
                "Type": "AWS::EC2::Instance",
                "Properties": {
                    "ImageId": {"Ref": "AmiId"},
                    "InstanceType": {"Ref": "InstanceType"},
                    "KeyName": {"Ref": "KeyPairName"},
                    "IamInstanceProfile": {"Ref": "IamInstanceProfileName"},
                    "SecurityGroupIds": [{"Ref": "SecurityGroupId"}],
                    "SubnetId": {"Ref": "VpcSubnetId"},
                    "UserData": {"Fn::Base64": {"Fn::Sub": user_data}},
                    "Tags": [{"Key": "Name", "Value": "claude-maverick"}],
                },
            },
        },
        "Outputs": {
            "WorkTableName": {
                "Value": {"Ref": "WorkTable"},
                "Description": "DynamoDB work table name",
            },
            "WorkTableArn": {
                "Value": {"Fn::GetAtt": ["WorkTable", "Arn"]},
                "Description": "DynamoDB work table ARN",
            },
            "FunctionUrl": {
                "Value": {"Fn::GetAtt": ["WebhookFunctionUrl", "FunctionUrl"]},
                "Description": "Lambda Function URL for GitHub webhook",
            },
            "LambdaArn": {
                "Value": {"Fn::GetAtt": ["WebhookFunction", "Arn"]},
                "Description": "Lambda function ARN",
            },
            "WorkerPolicyArn": {
                "Value": {"Ref": "WorkerPolicy"},
                "Description": "IAM policy ARN for EC2 workers",
            },
            "LogGroupName": {
                "Value": {"Ref": "WorkerLogGroup"},
                "Description": "CloudWatch log group name",
            },
            "InstanceId": {
                "Value": {"Ref": "WorkerInstance"},
                "Description": "EC2 worker instance ID",
            },
        },
    }


# ---------------------------------------------------------------------------
# CloudFormation operations
# ---------------------------------------------------------------------------


def _get_stack_outputs(cfn, stack_name):
    """Return stack outputs as {key: value} dict."""
    resp = cfn.describe_stacks(StackName=stack_name)
    outputs = resp["Stacks"][0].get("Outputs", [])
    return {o["OutputKey"]: o["OutputValue"] for o in outputs}


def _wait_for_stack(cfn, stack_name, target_statuses, failure_statuses):
    """Poll stack status until it reaches a target or failure state."""
    while True:
        resp = cfn.describe_stacks(StackName=stack_name)
        status = resp["Stacks"][0]["StackStatus"]
        if status in target_statuses:
            return status
        if status in failure_statuses:
            reason = resp["Stacks"][0].get("StackStatusReason", "unknown")
            raise InfraError(f"Stack '{stack_name}' reached {status}: {reason}")
        time.sleep(5)


def _create_or_update_stack(cfn, stack_name, template, parameters=None):
    """Create or update a CloudFormation stack. Handles common edge cases."""
    params = [{"ParameterKey": k, "ParameterValue": v} for k, v in (parameters or {}).items()]
    template_body = json.dumps(template)

    # Check if stack exists and its current state
    try:
        resp = cfn.describe_stacks(StackName=stack_name)
        stack_status = resp["Stacks"][0]["StackStatus"]
    except ClientError as e:
        if "does not exist" not in str(e):
            raise
        stack_status = None

    # Handle ROLLBACK_COMPLETE - must delete before recreating
    if stack_status == "ROLLBACK_COMPLETE":
        print(f"    Stack '{stack_name}' is in ROLLBACK_COMPLETE - deleting before recreate...")
        cfn.delete_stack(StackName=stack_name)
        _wait_for_stack(cfn, stack_name, {"DELETE_COMPLETE"}, {"DELETE_FAILED"})
        stack_status = None

    if stack_status is None:
        # Create
        print(f"    Creating stack '{stack_name}'...")
        cfn.create_stack(
            StackName=stack_name,
            TemplateBody=template_body,
            Parameters=params,
            Capabilities=["CAPABILITY_NAMED_IAM"],
        )
        _wait_for_stack(
            cfn,
            stack_name,
            {"CREATE_COMPLETE"},
            {"CREATE_FAILED", "ROLLBACK_COMPLETE", "ROLLBACK_FAILED"},
        )
    else:
        # Update
        print(f"    Updating stack '{stack_name}'...")
        try:
            cfn.update_stack(
                StackName=stack_name,
                TemplateBody=template_body,
                Parameters=params,
                Capabilities=["CAPABILITY_NAMED_IAM"],
            )
            _wait_for_stack(
                cfn,
                stack_name,
                {"UPDATE_COMPLETE"},
                {"UPDATE_FAILED", "UPDATE_ROLLBACK_COMPLETE", "UPDATE_ROLLBACK_FAILED"},
            )
        except ClientError as e:
            if "No updates are to be performed" in str(e):
                print(f"    Stack '{stack_name}' is already up to date.")
            else:
                raise


def _validate_key_pair(ec2, key_name):
    """Validate that an EC2 key pair exists. Raises InfraError if not found."""
    try:
        ec2.describe_key_pairs(KeyNames=[key_name])
    except ClientError as e:
        if "InvalidKeyPair.NotFound" in str(e):
            raise InfraError(
                f"EC2 key pair '{key_name}' not found. "
                "Create it in the AWS Console or with: "
                f"aws ec2 create-key-pair --key-name {key_name}"
            ) from e
        raise


def get_vpc_outputs(region):
    """Read VPC stack outputs into a dict. Raises InfraError if stack is missing."""
    cfn = boto3.client("cloudformation", region_name=region)
    try:
        outputs = _get_stack_outputs(cfn, VPC_STACK_NAME)
    except ClientError as e:
        if "does not exist" in str(e):
            raise InfraError(
                f"VPC stack '{VPC_STACK_NAME}' not found. "
                "Run 'maverick infra deploy' first to create prerequisites."
            ) from e
        raise
    expected = ("SubnetId", "SecurityGroupId", "InstanceProfileName", "RoleName", "SecretArn")
    missing = [k for k in expected if k not in outputs]
    if missing:
        raise InfraError(
            f"VPC stack is missing expected outputs: {', '.join(missing)}. "
            "Run 'maverick infra deploy' to update the stack."
        )
    return outputs


def _deploy_vpc_stack(cfn, region, ssh_cidr="0.0.0.0/0"):
    """Deploy or update the VPC stack. Returns outputs."""
    template = _build_vpc_template()
    parameters = {"SshCidr": ssh_cidr}
    _create_or_update_stack(cfn, VPC_STACK_NAME, template, parameters)
    return _get_stack_outputs(cfn, VPC_STACK_NAME)


def _delete_stack(cfn, stack_name):
    """Delete a CloudFormation stack and wait for completion."""
    try:
        cfn.describe_stacks(StackName=stack_name)
    except ClientError as e:
        if "does not exist" in str(e):
            print(f"    Stack '{stack_name}' does not exist - skipping.")
            return
        raise

    print(f"    Deleting stack '{stack_name}'...")
    cfn.delete_stack(StackName=stack_name)

    # Wait - after deletion describe_stacks raises if fully cleaned up
    while True:
        try:
            resp = cfn.describe_stacks(StackName=stack_name)
            status = resp["Stacks"][0]["StackStatus"]
            if status == "DELETE_COMPLETE":
                return
            if status == "DELETE_FAILED":
                reason = resp["Stacks"][0].get("StackStatusReason", "unknown")
                raise InfraError(f"Stack '{stack_name}' deletion failed: {reason}")
            time.sleep(5)
        except ClientError as e:
            if "does not exist" in str(e):
                return
            raise


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def deploy(ssh_cidr="0.0.0.0/0"):
    """Create or update all infrastructure resources."""
    try:
        _deploy_impl(ssh_cidr=ssh_cidr)
    except InfraError as e:
        print(f"\nError: {e}", file=sys.stderr)
        sys.exit(1)
    except ClientError as e:
        code = e.response["Error"]["Code"]
        msg = e.response["Error"]["Message"]
        print(f"\nAWS error ({code}): {msg}", file=sys.stderr)
        sys.exit(1)


def _deploy_impl(ssh_cidr="0.0.0.0/0"):
    # Check for legacy state file — require migration
    if INFRA_STATE.exists():
        raise InfraError(
            f"Legacy infrastructure state file found at {INFRA_STATE}.\n"
            "This version of maverick uses CloudFormation instead of imperative resource management.\n"
            "Please run 'maverick infra destroy' with the previous version first, then re-deploy.\n"
            "(The VPC will be preserved across destroy/redeploy.)"
        )

    cfg = init_config()
    region = cfg["aws"]["region"]

    # 0. Preflight: key_pair must be set in config (the one manual prerequisite)
    key_pair = cfg["aws"]["key_pair"]
    if not key_pair:
        raise InfraError(
            "aws.key_pair is not set in config.\n"
            "Create an EC2 key pair and add it to ~/.maverick/config.json:\n"
            '  "aws": { "key_pair": "your-key-name" }'
        )

    cfn = boto3.client("cloudformation", region_name=region)
    iam = boto3.client("iam")

    # 1. Validate EC2 key pair exists in AWS before creating any stacks
    print("==> Validating EC2 key pair...")
    ec2 = boto3.client("ec2", region_name=region)
    _validate_key_pair(ec2, key_pair)

    # 2. VPC stack (creates SG, IAM profile, Secret)
    print("==> Setting up VPC...")
    vpc_outputs = _deploy_vpc_stack(cfn, region, ssh_cidr=ssh_cidr)
    subnet_id = vpc_outputs["SubnetId"]
    security_group_id = vpc_outputs["SecurityGroupId"]
    instance_profile_name = vpc_outputs["InstanceProfileName"]
    role_name = vpc_outputs["RoleName"]
    secret_arn = vpc_outputs["SecretArn"]

    # 3. Resolve AMI — prefer maverick-baked, fall back to Ubuntu LTS
    print("==> Resolving AMI...")
    ami_id = _resolve_ami(region, cfg)

    # 4. Read Lambda handler source for inline embedding
    handler_path = Path(__file__).parent / "lambda_handler.py"
    lambda_code = handler_path.read_text()

    # 5. Prepare cloud-init user data for CFN embedding
    user_data = _prepare_user_data()

    # 6. Main infrastructure stack
    print("==> Deploying infrastructure stack...")
    template = _build_infra_template(lambda_code, user_data)
    parameters = {
        "SecretArn": secret_arn,
        "WebhookLabel": cfg["worker"]["webhook_label"],
        "LogGroupName": cfg["worker"]["cloudwatch_log_group"],
        "VpcSubnetId": subnet_id,
        "AmiId": ami_id,
        "InstanceType": cfg["instance"]["type"],
        "KeyPairName": key_pair,
        "SecurityGroupId": security_group_id,
        "IamInstanceProfileName": instance_profile_name,
    }
    _create_or_update_stack(cfn, STACK_NAME, template, parameters)

    # 7. Read outputs
    outputs = _get_stack_outputs(cfn, STACK_NAME)

    # 8. Attach worker policy to EC2 instance profile role (out-of-band)
    print("==> Attaching worker policy to EC2 role...")
    _ensure_role_policy_attachment(iam, role_name, outputs["WorkerPolicyArn"])

    # 9. Update config with VPC output values (backward compat)
    cfg["aws"]["work_table_name"] = outputs["WorkTableName"]
    cfg["aws"]["subnet"] = subnet_id
    cfg["aws"]["security_group"] = security_group_id
    cfg["aws"]["iam_profile"] = instance_profile_name
    cfg["aws"]["secret_arn"] = secret_arn
    save_config(cfg)

    # 10. Clean up legacy instance state if present
    INSTANCE_STATE.unlink(missing_ok=True)

    # 11. Get instance public IP
    instance_id = outputs["InstanceId"]
    ip = "pending"
    try:
        resp = ec2.describe_instances(InstanceIds=[instance_id])
        ip = resp["Reservations"][0]["Instances"][0].get("PublicIpAddress") or "pending"
    except ClientError:
        pass

    print()
    print("=== Infrastructure deployed ===")
    print(f"  VPC Subnet:     {subnet_id}")
    print(f"  Security Group: {security_group_id}")
    print(f"  IAM Profile:    {instance_profile_name}")
    print(f"  Secret ARN:     {secret_arn}")
    print(f"  DynamoDB Table: {outputs['WorkTableName']}")
    print(f"  Lambda:         {outputs['LambdaArn']}")
    print(f"  Function URL:   {outputs['FunctionUrl']}")
    print(f"  Log Group:      {outputs['LogGroupName']}")
    print(f"  Worker Policy:  {outputs['WorkerPolicyArn']}")
    print(f"  Instance:       {instance_id}")
    print(f"  Public IP:      {ip}")
    if ip and ip != "pending":
        print(f"  SSH:            ssh claude@{ip}")
    print()
    print("Next steps:")
    print("  1. Update secret values in AWS Console (Secrets Manager)")
    print("  2. Configure this Function URL as a GitHub webhook")
    print(f"     URL:    {outputs['FunctionUrl']}")
    print("     Events: Issues")
    print("     Secret: The GITHUB_WEBHOOK_SECRET value from your secret")


def status():
    """Show current infrastructure resource status."""
    try:
        return _status_impl()
    except InfraError as e:
        print(f"\nError: {e}", file=sys.stderr)
        sys.exit(1)
    except ClientError as e:
        code = e.response["Error"]["Code"]
        msg = e.response["Error"]["Message"]
        print(f"\nAWS error ({code}): {msg}", file=sys.stderr)
        sys.exit(1)


def _status_impl():
    cfg = init_config()
    region = cfg["aws"]["region"]
    cfn = boto3.client("cloudformation", region_name=region)

    # VPC stack
    vpc_status = "not deployed"
    vpc_outputs = {}
    try:
        resp = cfn.describe_stacks(StackName=VPC_STACK_NAME)
        vpc_status = resp["Stacks"][0]["StackStatus"]
        vpc_outputs = _get_stack_outputs(cfn, VPC_STACK_NAME)
    except ClientError as e:
        if "does not exist" not in str(e):
            raise

    # Infra stack
    infra_status = "not deployed"
    infra_outputs = {}
    try:
        resp = cfn.describe_stacks(StackName=STACK_NAME)
        infra_status = resp["Stacks"][0]["StackStatus"]
        infra_outputs = _get_stack_outputs(cfn, STACK_NAME)
    except ClientError as e:
        if "does not exist" not in str(e):
            raise

    if infra_status == "not deployed" and vpc_status == "not deployed":
        print("No infrastructure deployed. Run 'maverick infra deploy' first.")
        sys.exit(1)

    # Instance live state
    instance_id = infra_outputs.get("InstanceId")
    instance_state = "N/A"
    instance_ip = "N/A"
    if instance_id:
        try:
            ec2 = boto3.client("ec2", region_name=region)
            resp = ec2.describe_instances(InstanceIds=[instance_id])
            inst = resp["Reservations"][0]["Instances"][0]
            instance_state = inst["State"]["Name"]
            instance_ip = inst.get("PublicIpAddress") or "None"
        except ClientError:
            pass

    print("=== Infrastructure Status ===")
    print(f"  VPC Stack:      {VPC_STACK_NAME} ({vpc_status})")
    print(f"    VPC:          {vpc_outputs.get('VpcId', 'N/A')}")
    print(f"    Subnet:       {vpc_outputs.get('SubnetId', 'N/A')}")
    print(f"    Security Grp: {vpc_outputs.get('SecurityGroupId', 'N/A')}")
    print(f"    IAM Profile:  {vpc_outputs.get('InstanceProfileName', 'N/A')}")
    print(f"    IAM Role:     {vpc_outputs.get('RoleName', 'N/A')}")
    print(f"    Secret ARN:   {vpc_outputs.get('SecretArn', 'N/A')}")
    print(f"  Infra Stack:    {STACK_NAME} ({infra_status})")
    print(f"    DynamoDB:     {infra_outputs.get('WorkTableName', 'N/A')}")
    print(f"    Lambda:       {infra_outputs.get('LambdaArn', 'N/A')}")
    print(f"    Function URL: {infra_outputs.get('FunctionUrl', 'N/A')}")
    print(f"    Log Group:    {infra_outputs.get('LogGroupName', 'N/A')}")
    print(f"    Worker Policy:{infra_outputs.get('WorkerPolicyArn', 'N/A')}")
    print(f"    Instance:     {instance_id or 'N/A'} ({instance_state})")
    print(f"    Public IP:    {instance_ip}")


def destroy(include_vpc=False):
    """Tear down all infrastructure resources."""
    try:
        return _destroy_impl(include_vpc=include_vpc)
    except InfraError as e:
        print(f"\nError: {e}", file=sys.stderr)
        sys.exit(1)
    except (NoCredentialsError, PartialCredentialsError):
        print(
            "\nError: AWS credentials not found. Configure credentials before destroying infrastructure.",
            file=sys.stderr,
        )
        sys.exit(1)
    except ClientError as e:
        code = e.response["Error"]["Code"]
        msg = e.response["Error"]["Message"]
        print(f"\nAWS error ({code}): {msg}", file=sys.stderr)
        sys.exit(1)


def _destroy_impl(include_vpc=False):
    cfg = init_config()
    region = cfg["aws"]["region"]
    cfn = boto3.client("cloudformation", region_name=region)
    iam = boto3.client("iam")

    # Check if anything is deployed
    infra_exists = True
    try:
        cfn.describe_stacks(StackName=STACK_NAME)
    except ClientError as e:
        if "does not exist" in str(e):
            infra_exists = False
        else:
            raise

    vpc_exists = True
    try:
        cfn.describe_stacks(StackName=VPC_STACK_NAME)
    except ClientError as e:
        if "does not exist" in str(e):
            vpc_exists = False
        else:
            raise

    if not infra_exists and not vpc_exists and not INFRA_STATE.exists():
        print("No infrastructure to destroy.")
        return

    what = "all maverick infrastructure"
    if include_vpc:
        what += " including VPC"
    confirm = input(f"Destroy {what}? This cannot be undone. [y/N] ")
    if confirm.lower() != "y":
        print("Cancelled.")
        return

    # Detach worker policy from EC2 role before stack deletion
    if infra_exists:
        print("==> Detaching worker policy from EC2 role...")
        try:
            outputs = _get_stack_outputs(cfn, STACK_NAME)
            # Prefer VPC stack output for role name, fall back to config
            try:
                vpc_outputs = _get_stack_outputs(cfn, VPC_STACK_NAME)
                ec2_role_name = vpc_outputs.get("RoleName")
            except ClientError:
                ec2_role_name = None
            if not ec2_role_name:
                ec2_role_name = _get_role_name_from_profile(
                    iam, cfg["aws"].get("iam_profile", "")
                )
            iam.detach_role_policy(
                RoleName=ec2_role_name,
                PolicyArn=outputs.get("WorkerPolicyArn", ""),
            )
        except (ClientError, InfraError):
            pass

    # Delete main infrastructure stack
    if infra_exists:
        print("==> Deleting infrastructure stack...")
        _delete_stack(cfn, STACK_NAME)

    # Delete VPC stack if requested
    if include_vpc and vpc_exists:
        print("==> Deleting VPC stack...")
        _delete_stack(cfn, VPC_STACK_NAME)

    # Clean up config
    cfg["aws"].pop("work_table_name", None)
    cfg["aws"].pop("sqs_queue_url", None)  # Clean up old SQS config if present
    save_config(cfg)

    # Remove legacy state files if present
    INFRA_STATE.unlink(missing_ok=True)
    INSTANCE_STATE.unlink(missing_ok=True)

    print()
    print("=== Infrastructure destroyed ===")
    if not include_vpc and vpc_exists:
        print("  Note: VPC stack preserved. Use --include-vpc to also destroy it.")
