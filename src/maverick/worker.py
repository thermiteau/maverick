"""DynamoDB worker daemon — polls for issues, runs Claude Code, logs to CloudWatch."""

import shutil
import subprocess
import sys
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import boto3
from botocore.exceptions import ClientError

from maverick.config import init_config

SYSTEMD_UNIT = Path("/etc/systemd/system/maverick-worker.service")
WORKER_ID = str(uuid.uuid4())


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


def _claim_item(dynamodb, table_name, item):
    """Attempt to claim a work item via conditional update. Returns True if claimed."""
    now = datetime.now(timezone.utc)
    lock_until = (now + timedelta(minutes=15)).strftime("%Y-%m-%dT%H:%M:%SZ")
    now_str = now.strftime("%Y-%m-%dT%H:%M:%SZ")

    try:
        dynamodb.update_item(
            TableName=table_name,
            Key={"id": item["id"]},
            UpdateExpression=(
                "SET #s = :processing, locked_until = :lock, worker_id = :wid, "
                "receive_count = receive_count + :one"
            ),
            ConditionExpression=(
                "#s = :pending OR (#s = :processing AND locked_until < :now)"
            ),
            ExpressionAttributeNames={"#s": "status"},
            ExpressionAttributeValues={
                ":processing": {"S": "PROCESSING"},
                ":pending": {"S": "PENDING"},
                ":lock": {"S": lock_until},
                ":wid": {"S": WORKER_ID},
                ":now": {"S": now_str},
                ":one": {"N": "1"},
            },
        )
        return True
    except ClientError as e:
        if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
            return False
        raise


def _complete_item(dynamodb, table_name, item_id):
    """Mark a work item as completed."""
    dynamodb.update_item(
        TableName=table_name,
        Key={"id": {"S": item_id}},
        UpdateExpression="SET #s = :completed",
        ExpressionAttributeNames={"#s": "status"},
        ExpressionAttributeValues={":completed": {"S": "COMPLETED"}},
    )


def _fail_item(dynamodb, table_name, item_id, receive_count, max_attempts):
    """Mark a work item as FAILED if max attempts reached, else reset to PENDING."""
    if receive_count >= max_attempts:
        new_status = "FAILED"
    else:
        new_status = "PENDING"

    dynamodb.update_item(
        TableName=table_name,
        Key={"id": {"S": item_id}},
        UpdateExpression="SET #s = :status",
        ExpressionAttributeNames={"#s": "status"},
        ExpressionAttributeValues={":status": {"S": new_status}},
    )


def _poll_candidates(dynamodb, table_name):
    """Query for PENDING items and stale PROCESSING items."""
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    candidates = []

    # Query PENDING items via GSI
    resp = dynamodb.query(
        TableName=table_name,
        IndexName="status-created_at-index",
        KeyConditionExpression="#s = :pending",
        ExpressionAttributeNames={"#s": "status"},
        ExpressionAttributeValues={":pending": {"S": "PENDING"}},
        Limit=5,
    )
    candidates.extend(resp.get("Items", []))

    # Also query stale PROCESSING items (crashed workers)
    resp = dynamodb.query(
        TableName=table_name,
        IndexName="status-created_at-index",
        KeyConditionExpression="#s = :processing",
        FilterExpression="locked_until < :now",
        ExpressionAttributeNames={"#s": "status"},
        ExpressionAttributeValues={
            ":processing": {"S": "PROCESSING"},
            ":now": {"S": now_str},
        },
        Limit=5,
    )
    candidates.extend(resp.get("Items", []))

    return candidates


def _process_item(item, cfg, dynamodb, logs_client):
    """Process a single work item: clone, run Claude, clean up."""
    item_id = item["id"]["S"]
    repo = item["repo"]["S"]
    issue_number = int(item["issue_number"]["N"])
    clone_url = item["clone_url"]["S"]
    receive_count = int(item["receive_count"]["N"])
    table_name = cfg["aws"]["work_table_name"]
    max_attempts = cfg["queue"]["max_attempts"]

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
        cw.log(f'Running: claude -p "{prompt}"')

        proc = subprocess.Popen(
            ["claude", "-p", prompt],
            cwd=clone_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )

        if proc.stdout is not None:
            for line in proc.stdout:
                line = line.rstrip("\n")
                if line:
                    cw.log(line)

        proc.wait()

        if proc.returncode != 0:
            cw.log(f"Claude exited with code {proc.returncode}")
            raise RuntimeError(f"Claude exited with code {proc.returncode}")

        # Success — mark completed
        cw.log(f"Completed {repo}#{issue_number}")
        _complete_item(dynamodb, table_name, item_id)

    except Exception as e:
        cw.log(f"Failed: {e}")
        _fail_item(dynamodb, table_name, item_id, receive_count, max_attempts)
        raise

    finally:
        # Clean up clone directory
        if clone_dir.exists():
            shutil.rmtree(clone_dir, ignore_errors=True)


def _poll_loop(cfg):
    """Main polling loop — processes one item at a time."""
    region = cfg["aws"]["region"]
    dynamodb = boto3.client("dynamodb", region_name=region)
    logs_client = boto3.client("logs", region_name=region)
    table_name = cfg["aws"]["work_table_name"]

    print(f"Worker {WORKER_ID} polling {table_name}...")

    while True:
        try:
            candidates = _poll_candidates(dynamodb, table_name)
            if not candidates:
                time.sleep(5)
                continue

            for item in candidates:
                if not _claim_item(dynamodb, table_name, item):
                    continue

                repo = item["repo"]["S"]
                issue_number = item["issue_number"]["N"]
                print(f"Processing {repo}#{issue_number}...")

                try:
                    _process_item(item, cfg, dynamodb, logs_client)
                    print("  Done.")
                except Exception as e:
                    print(f"  Failed: {e}")
                break  # Process one item per poll cycle

        except KeyboardInterrupt:
            print("\nWorker stopped.")
            break
        except Exception as e:
            print(f"Poll error: {e}")
            time.sleep(5)


def run_once(cfg):
    """Process a single item and exit. For testing."""
    region = cfg["aws"]["region"]
    dynamodb = boto3.client("dynamodb", region_name=region)
    logs_client = boto3.client("logs", region_name=region)
    table_name = cfg["aws"]["work_table_name"]

    print("Checking table for pending work...")
    candidates = _poll_candidates(dynamodb, table_name)
    if not candidates:
        print("No pending items.")
        return

    for item in candidates:
        if not _claim_item(dynamodb, table_name, item):
            continue

        repo = item["repo"]["S"]
        issue_number = item["issue_number"]["N"]
        print(f"Processing {repo}#{issue_number}...")
        _process_item(item, cfg, dynamodb, logs_client)
        print("Done.")
        return

    print("No items could be claimed.")


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
        if not cfg["aws"].get("work_table_name"):
            print("Error: No DynamoDB table configured. Run 'maverick infra deploy' first.")
            sys.exit(1)
        _poll_loop(cfg)
    elif action == "run-once":
        cfg = init_config()
        if not cfg["aws"].get("work_table_name"):
            print("Error: No DynamoDB table configured. Run 'maverick infra deploy' first.")
            sys.exit(1)
        run_once(cfg)
