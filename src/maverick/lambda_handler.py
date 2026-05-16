"""GitHub webhook handler — validates signature, filters label events, writes to DynamoDB."""

import hashlib
import hmac
import json
import os
import uuid
from datetime import datetime, timezone

import boto3


def lambda_handler(event, context):
    """AWS Lambda entry point for GitHub webhook via Function URL."""
    work_table_name = os.environ["WORK_TABLE_NAME"]
    secret_arn = os.environ["SECRET_ARN"]
    webhook_label = os.environ.get("WEBHOOK_LABEL", "claude-do")

    # Extract headers and body from Function URL event
    headers = {k.lower(): v for k, v in event.get("headers", {}).items()}
    body = event.get("body", "")
    if event.get("isBase64Encoded"):
        import base64

        body = base64.b64decode(body).decode("utf-8")

    # Verify webhook signature
    signature = headers.get("x-hub-signature-256", "")
    if not signature:
        return {"statusCode": 401, "body": "Missing signature"}

    sm = boto3.client("secretsmanager")
    secret_value = json.loads(sm.get_secret_value(SecretId=secret_arn)["SecretString"])
    webhook_secret = secret_value["GITHUB_WEBHOOK_SECRET"]

    expected = (
        "sha256=" + hmac.new(webhook_secret.encode(), body.encode(), hashlib.sha256).hexdigest()
    )

    if not hmac.compare_digest(signature, expected):
        return {"statusCode": 401, "body": "Invalid signature"}

    # Parse payload
    payload = json.loads(body)
    action = payload.get("action")
    label_name = payload.get("label", {}).get("name")

    # Filter: only "labeled" action with the target label
    if action != "labeled" or label_name != webhook_label:
        return {"statusCode": 200, "body": "Ignored"}

    # Build DynamoDB item
    repo = payload["repository"]["full_name"]
    issue_number = payload["issue"]["number"]
    clone_url = payload["repository"]["clone_url"]
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    item = {
        "id": {"S": str(uuid.uuid4())},
        "status": {"S": "PENDING"},
        "repo": {"S": repo},
        "issue_number": {"N": str(issue_number)},
        "clone_url": {"S": clone_url},
        "triggered_at": {"S": now},
        "created_at": {"S": now},
        "receive_count": {"N": "0"},
    }

    dynamodb = boto3.client("dynamodb")
    dynamodb.put_item(TableName=work_table_name, Item=item)

    return {"statusCode": 200, "body": f"Queued {repo}#{issue_number}"}
