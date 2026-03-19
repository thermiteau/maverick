"""Tests for maverick.lambda_handler — GitHub webhook validation and routing."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
from unittest.mock import MagicMock, patch

import pytest


def _sign(body: str, secret: str) -> str:
    """Compute the expected GitHub webhook HMAC-SHA256 signature."""
    return "sha256=" + hmac.new(secret.encode(), body.encode(), hashlib.sha256).hexdigest()


def _make_event(
    body: str,
    signature: str | None = None,
    base64_encoded: bool = False,
) -> dict:
    """Build a minimal Lambda Function URL event."""
    headers: dict[str, str] = {}
    if signature is not None:
        headers["x-hub-signature-256"] = signature

    raw_body = base64.b64encode(body.encode()).decode() if base64_encoded else body

    return {
        "headers": headers,
        "body": raw_body,
        "isBase64Encoded": base64_encoded,
    }


def _labeled_payload(
    repo: str = "org/repo",
    issue_number: int = 42,
    label: str = "claude-do",
) -> str:
    return json.dumps({
        "action": "labeled",
        "label": {"name": label},
        "repository": {
            "full_name": repo,
            "clone_url": f"https://github.com/{repo}.git",
        },
        "issue": {"number": issue_number},
    })


@pytest.fixture(autouse=True)
def _env_vars(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("SQS_QUEUE_URL", "https://sqs.us-east-1.amazonaws.com/123/queue")
    monkeypatch.setenv("SECRET_ARN", "arn:aws:secretsmanager:us-east-1:123:secret:webhook")


@pytest.fixture
def mock_boto3():
    with patch("maverick.lambda_handler.boto3") as m:
        sm_client = MagicMock()
        sqs_client = MagicMock()
        m.client.side_effect = lambda service: {
            "secretsmanager": sm_client,
            "sqs": sqs_client,
        }[service]
        sm_client.get_secret_value.return_value = {
            "SecretString": json.dumps({"GITHUB_WEBHOOK_SECRET": "test-secret"})
        }
        yield {"sm": sm_client, "sqs": sqs_client}


class TestLambdaHandler:
    def test_missing_signature_returns_401(self, mock_boto3):
        from maverick.lambda_handler import lambda_handler

        event = _make_event(body="{}", signature=None)
        result = lambda_handler(event, None)
        assert result["statusCode"] == 401
        assert "Missing signature" in result["body"]

    def test_invalid_signature_returns_401(self, mock_boto3):
        from maverick.lambda_handler import lambda_handler

        body = _labeled_payload()
        event = _make_event(body=body, signature="sha256=bad")
        result = lambda_handler(event, None)
        assert result["statusCode"] == 401
        assert "Invalid signature" in result["body"]

    def test_valid_signature_non_labeled_action_ignored(self, mock_boto3):
        from maverick.lambda_handler import lambda_handler

        body = json.dumps({"action": "opened", "label": {"name": "claude-do"}})
        event = _make_event(body=body, signature=_sign(body, "test-secret"))
        result = lambda_handler(event, None)
        assert result["statusCode"] == 200
        assert result["body"] == "Ignored"

    def test_valid_signature_wrong_label_ignored(self, mock_boto3):
        from maverick.lambda_handler import lambda_handler

        body = _labeled_payload(label="bug")
        event = _make_event(body=body, signature=_sign(body, "test-secret"))
        result = lambda_handler(event, None)
        assert result["statusCode"] == 200
        assert result["body"] == "Ignored"

    def test_valid_labeled_event_enqueues(self, mock_boto3):
        from maverick.lambda_handler import lambda_handler

        body = _labeled_payload(repo="myorg/myrepo", issue_number=99)
        event = _make_event(body=body, signature=_sign(body, "test-secret"))
        result = lambda_handler(event, None)

        assert result["statusCode"] == 200
        assert "myorg/myrepo#99" in result["body"]

        # Verify SQS was called
        mock_boto3["sqs"].send_message.assert_called_once()
        call_kwargs = mock_boto3["sqs"].send_message.call_args[1]
        msg = json.loads(call_kwargs["MessageBody"])
        assert msg["repo"] == "myorg/myrepo"
        assert msg["issue_number"] == 99

    def test_base64_encoded_body(self, mock_boto3):
        from maverick.lambda_handler import lambda_handler

        body = _labeled_payload()
        event = _make_event(body=body, signature=_sign(body, "test-secret"), base64_encoded=True)
        result = lambda_handler(event, None)
        assert result["statusCode"] == 200
        assert "Queued" in result["body"]

    def test_custom_webhook_label(self, mock_boto3, monkeypatch: pytest.MonkeyPatch):
        from maverick.lambda_handler import lambda_handler

        monkeypatch.setenv("WEBHOOK_LABEL", "auto-fix")
        body = _labeled_payload(label="auto-fix")
        event = _make_event(body=body, signature=_sign(body, "test-secret"))
        result = lambda_handler(event, None)
        assert result["statusCode"] == 200
        assert "Queued" in result["body"]
