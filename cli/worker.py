"""SQS worker daemon — polls for issues, runs Claude Code, logs to CloudWatch."""

import json
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import boto3
from botocore.exceptions import ClientError

from maverick.config import init_config

SYSTEMD_UNIT = Path("/etc/systemd/system/maverick-worker.service")


class CloudWatchLogger:
    """Stream log lines to a CloudWatch log stream."""

    def __init__(self, logs_client, log_group, stream_name):
        self.logs = logs_client
        self.log_group = log_group
        self.stream_name = stream_name
        self.sequence_token = None
        self._ensure_stream()

    def _ensure_stream(self):
        try:
            self.logs.create_log_stream(
                logGroupName=self.log_group,
                logStreamName=self.stream_name,
            )
        except ClientError as e:
            if e.response["Error"]["Code"] != "ResourceAlreadyExistsException":
                raise

    def log(self, message):
        """Send a single log line to CloudWatch."""
        timestamp = int(datetime.now(timezone.utc).timestamp() * 1000)
        kwargs = {
            "logGroupName": self.log_group,
            "logStreamName": self.stream_name,
            "logEvents": [{"timestamp": timestamp, "message": message}],
        }
        if self.sequence_token:
            kwargs["sequenceToken"] = self.sequence_token
        try:
            resp = self.logs.put_log_events(**kwargs)
            self.sequence_token = resp.get("nextSequenceToken")
        except ClientError:
            # Best-effort logging — don't crash the worker over a log failure
            pass


def _process_message(message, cfg, sqs, logs_client):
    """Process a single SQS message: clone, run Claude, clean up."""
    body = json.loads(message["Body"])
    repo = body["repo"]
    issue_number = body["issue_number"]
    clone_url = body["clone_url"]

    owner_repo = repo.replace("/", "-")
    stream_name = f"{owner_repo}-{issue_number}"
    work_dir = Path(cfg["worker"]["work_dir"])
    clone_dir = work_dir / f"{owner_repo}-{issue_number}"

    log_group = cfg["worker"]["cloudwatch_log_group"]
    cw = CloudWatchLogger(logs_client, log_group, stream_name)
    cw.log(f"Starting work on {repo}#{issue_number}")

    try:
        # Clone
        clone_dir.parent.mkdir(parents=True, exist_ok=True)
        if clone_dir.exists():
            shutil.rmtree(clone_dir)

        cw.log(f"Cloning {clone_url}...")
        subprocess.run(
            ["git", "clone", clone_url, str(clone_dir)],
            check=True,
            capture_output=True,
            text=True,
        )

        # Run Claude Code
        prompt_template = cfg["worker"]["prompt_template"]
        prompt = prompt_template.format(issue_number=issue_number)
        cw.log(f"Running: claude -p \"{prompt}\"")

        proc = subprocess.Popen(
            ["claude", "-p", prompt],
            cwd=clone_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )

        for line in proc.stdout:
            line = line.rstrip("\n")
            if line:
                cw.log(line)

        proc.wait()

        if proc.returncode != 0:
            cw.log(f"Claude exited with code {proc.returncode}")
            raise RuntimeError(f"Claude exited with code {proc.returncode}")

        # Success — delete SQS message
        cw.log(f"Completed {repo}#{issue_number}")
        sqs.delete_message(
            QueueUrl=cfg["aws"]["sqs_queue_url"],
            ReceiptHandle=message["ReceiptHandle"],
        )

    except Exception as e:
        cw.log(f"Failed: {e}")
        # Don't delete message — visibility timeout will expire and it returns to queue
        raise

    finally:
        # Clean up clone directory
        if clone_dir.exists():
            shutil.rmtree(clone_dir, ignore_errors=True)


def _poll_loop(cfg):
    """Main polling loop — processes one message at a time."""
    region = cfg["aws"]["region"]
    sqs = boto3.client("sqs", region_name=region)
    logs_client = boto3.client("logs", region_name=region)
    queue_url = cfg["aws"]["sqs_queue_url"]

    print(f"Worker polling {queue_url}...")

    while True:
        try:
            resp = sqs.receive_message(
                QueueUrl=queue_url,
                MaxNumberOfMessages=1,
                WaitTimeSeconds=20,
            )
            messages = resp.get("Messages", [])
            if not messages:
                continue

            message = messages[0]
            body = json.loads(message["Body"])
            print(f"Processing {body['repo']}#{body['issue_number']}...")

            try:
                _process_message(message, cfg, sqs, logs_client)
                print(f"  Done.")
            except Exception as e:
                print(f"  Failed: {e}")

        except KeyboardInterrupt:
            print("\nWorker stopped.")
            break
        except Exception as e:
            print(f"Poll error: {e}")
            time.sleep(5)


def run_once(cfg):
    """Process a single message and exit. For testing."""
    region = cfg["aws"]["region"]
    sqs = boto3.client("sqs", region_name=region)
    logs_client = boto3.client("logs", region_name=region)
    queue_url = cfg["aws"]["sqs_queue_url"]

    print(f"Checking queue for one message...")
    resp = sqs.receive_message(
        QueueUrl=queue_url,
        MaxNumberOfMessages=1,
        WaitTimeSeconds=5,
    )
    messages = resp.get("Messages", [])
    if not messages:
        print("No messages in queue.")
        return

    message = messages[0]
    body = json.loads(message["Body"])
    print(f"Processing {body['repo']}#{body['issue_number']}...")
    _process_message(message, cfg, sqs, logs_client)
    print("Done.")


def install(cfg):
    """Install and start the systemd service."""
    maverick_path = shutil.which("maverick")
    if not maverick_path:
        print("Error: 'maverick' not found in PATH. Install with: uv tool install .")
        sys.exit(1)

    worker_user = cfg["worker"]["user"]
    worker_home = f"/home/{worker_user}"

    unit_content = f"""\
[Unit]
Description=Maverick Worker - Claude Code issue processor
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User={worker_user}
ExecStart={maverick_path} worker start
Restart=on-failure
RestartSec=10
Environment=HOME={worker_home}
WorkingDirectory={worker_home}

[Install]
WantedBy=multi-user.target
"""

    print("==> Installing systemd service...")
    SYSTEMD_UNIT.write_text(unit_content)
    subprocess.run(["systemctl", "daemon-reload"], check=True)
    subprocess.run(["systemctl", "enable", "maverick-worker"], check=True)
    subprocess.run(["systemctl", "start", "maverick-worker"], check=True)
    print("    Service installed and started.")
    print("    Check status with: maverick worker status")


def uninstall():
    """Stop and remove the systemd service."""
    print("==> Removing systemd service...")
    subprocess.run(["systemctl", "stop", "maverick-worker"], check=False)
    subprocess.run(["systemctl", "disable", "maverick-worker"], check=False)
    if SYSTEMD_UNIT.exists():
        SYSTEMD_UNIT.unlink()
    subprocess.run(["systemctl", "daemon-reload"], check=True)
    print("    Service removed.")


def worker_status():
    """Show systemd service status."""
    result = subprocess.run(
        ["systemctl", "status", "maverick-worker"],
        capture_output=True,
        text=True,
    )
    print(result.stdout)
    if result.stderr:
        print(result.stderr)


def main(action):
    """Entry point called from cli.py."""
    if action == "install":
        cfg = init_config()
        install(cfg)
    elif action == "uninstall":
        uninstall()
    elif action == "status":
        worker_status()
    elif action == "start":
        cfg = init_config()
        if not cfg["aws"].get("sqs_queue_url"):
            print("Error: No SQS queue configured. Run 'maverick infra deploy' first.")
            sys.exit(1)
        _poll_loop(cfg)
    elif action == "run-once":
        cfg = init_config()
        if not cfg["aws"].get("sqs_queue_url"):
            print("Error: No SQS queue configured. Run 'maverick infra deploy' first.")
            sys.exit(1)
        run_once(cfg)
