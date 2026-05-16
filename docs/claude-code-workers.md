---
title: Claude Code Workers
scope: Remote compute instances running Claude Code
relates-to:
  - cicd.md
  - maverick-build.md
last-verified: 2026-03-20
---

## Remote Compute

Maverick completes development tasks autonomously at scale using cloud infrastructure to create a pipeline of work feeding worker instances.

GitHub webhook → Lambda → DynamoDB → EC2 worker → Claude Code.

Remote instances support two usage models:

1. **Event-driven and autonomous.** GitHub triggers an event that writes a request to a DynamoDB work table. A compute instance polls the table, claims an item, and completes it autonomously.

2. **Manual request.** SSH into the instance and interact with Claude Code directly using Maverick plugin commands, just as you would locally.

## Infrastructure Deployment

Maverick provides two ways to deploy the AWS infrastructure: the **CLI** (recommended) and **standalone CloudFormation templates** for manual deployment.

### Option 1: CLI Deployment

The CLI wraps CloudFormation with AMI resolution, config management, and policy attachment. Two stacks are created:

**`maverick-vpc`** — networking and prerequisites (preserved on destroy by default):
- VPC (`10.0.0.0/16`), Internet Gateway, Public Subnet (`10.0.1.0/24`), Route Table
- Security Group (SSH inbound, all outbound)
- IAM Role + Instance Profile for the worker
- Secrets Manager Secret (placeholder values — update after first deploy)

**`maverick-infra`** — application resources and compute:
- DynamoDB Table (`maverick-work`) with GSI and TTL
- Lambda Function (`maverick-webhook`) with Function URL
- IAM roles and policies (Lambda execution, EC2 worker)
- CloudWatch Log Group
- EC2 Worker Instance (cloud-init provisioned)

The only manual prerequisite is an **EC2 key pair** — create one before running `maverick infra deploy`. All other prerequisites (security group, IAM profile, secret) are created automatically by the VPC stack.

AMI selection is automatic: if a maverick-baked AMI exists (via `maverick build-ami`), it is used. Otherwise, Ubuntu 24.04 LTS is resolved via AWS SSM Parameter Store as a fallback. In both cases the bundled cloud-init configuration is applied as UserData.

```sh
maverick infra deploy     # Create or update both stacks
maverick infra status     # Show stack outputs and instance state
maverick infra destroy    # Delete infra stack (VPC preserved)
maverick infra destroy --include-vpc  # Also delete VPC stack
```

### Option 2: Standalone CloudFormation Templates

Pre-built CloudFormation templates are available in the `infra/` directory at the project root. These are generated as part of the `make build` process and contain the same resource definitions used by the CLI.

| Template | Purpose | Parameters |
|----------|---------|------------|
| `infra/maverick-vpc.template.json` | VPC networking + prerequisites | `SshCidr` (default: `0.0.0.0/0`) |
| `infra/maverick-infra.template.json` | Application resources + EC2 instance | `SecretArn`, `AmiId`, `InstanceType`, `KeyPairName`, `SecurityGroupId`, `IamInstanceProfileName`, `VpcSubnetId`, `WebhookLabel`, `LogGroupName` |

The VPC template outputs `SecurityGroupId`, `InstanceProfileName`, `RoleName`, and `SecretArn` — use these as inputs to the infra template.

To use the standalone templates:

1. Upload `maverick-vpc.template.json` to CloudFormation and create the stack.
2. Upload `maverick-infra.template.json`, fill in the parameters using the VPC stack outputs and your AWS resource IDs, and create the stack.
3. Manually attach the `WorkerPolicyArn` (from the infra stack outputs) to your EC2 instance profile role.

The standalone templates do not manage the worker policy attachment to your EC2 role — this is the one step the CLI automates that the templates cannot.

> **Migration note:** If upgrading from a version that used imperative boto3 resource management (with `~/.maverick/infra_state.json`), run `maverick infra destroy` with the previous version first, then re-deploy. The VPC is preserved across destroy/redeploy.

## Compute Instances

### Build AMI (Optional)

Bake a Linux AMI pre-configured with Claude Code using cloud-init. This step is optional — if no baked AMI exists, `maverick infra deploy` falls back to Ubuntu 24.04 LTS with cloud-init provisioning at instance launch.

```sh
maverick build-ami
```

The `build-ami` command requires `maverick infra deploy` to have been run first — it reads the security group, IAM profile, subnet, and secret ARN from the VPC stack outputs. The only config value needed is the EC2 key pair name.

The script will:

1. Look up the latest Ubuntu 24.04 LTS AMI via SSM Parameter Store
2. Launch a build instance with cloud-init user-data
3. Wait for provisioning to complete (~10-15 minutes)
4. Stop the instance and create an AMI
5. Terminate the build instance
6. Save the AMI ID to `~/.maverick/ami_state.json`

### Manage Instances

The worker instance is created and terminated as part of the `maverick-infra` CloudFormation stack. The `maverick instance` commands manage runtime state:

```sh
maverick instance start       # Start a stopped instance
maverick instance stop        # Stop a running instance
maverick instance status      # Show instance details
```

### Worker Commands

Worker output is streamed to CloudWatch Logs at `/maverick/worker` with one stream per issue.

If you SSH into a worker, you can run the following commands:

```sh
maverick infra status        # Show stack outputs and resource ARNs
maverick worker status       # Show systemd service status
maverick worker uninstall    # Remove systemd service
maverick worker run-once     # Process one message (testing)
```

## GitHub Webhook

In your GitHub repo: Settings → Webhooks → Add webhook:

- **Payload URL:** The Function URL from `maverick infra status` or the `FunctionUrl` stack output
- **Content type:** `application/json`
- **Secret:** The value of `GITHUB_WEBHOOK_SECRET` in your Secrets Manager secret
- **Events:** Select "Issues"
