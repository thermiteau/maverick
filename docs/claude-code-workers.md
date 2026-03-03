---
title: Claude Code Workers
scope: Remote compute instances running Claude Code
relates-to:  
  - cicd.md
last-verified: 2026-03-02
---

## Remote Compute

Maverick is designed to complete development tasks as autonomously as possible, at scale. To acheive this Cloud infrastructure is used to create a pipeline of work feeding worker instances.

GitHub webhook → SQS → EC2 worker → Claude Code.

Using Maverick on remote instances can be done in two different ways, depending on your requirements.

1) Event driven and autonomous.

Under this model, Github will trigger an event that puts the request into the message queue. Compute instances will read the queue, take an issue and complete it autonomously.

1) Manual request

Under this model, you need to remote into the instance via SSH and interact with the Claude Code CLI and use Marketick PLugion commands. just like you would locally. The task will be completed autonomously, but you can see the Cluade interface output.

### Deploy infrastructure

By default maverick builds on AWS. The following resources are deployed:

- 1 x EC2 AMI
- 1 EC2 Instance
  - Instance IAM Policy
  - Security Group
- 1 SQS Message Queue
  - SQS IAM Policy
- 1 Lambda Function
  - Lambda IAM Policy
- Parameter Store Entry
  - Parameter Store IAM Policy

```sh
maverick cloud init
```

- 
### Compute Instances (AWS)

Compute instances are built to receive development tasks, process them and commit results back to source ceontrol. AWS EC2 is supported out of the box.

#### Build AMI

Bake a Linux (Ubuntu 24.04 LTS by default) AMI pre-configured with Claude Code using the cloud-init config.

```sh
maverick build-ami
```

On first run, a starter config is created at `~/.maverick/config.toml`. Edit it with your AWS values (region, key pair, security group, IAM profile, secret ARN) then re-run.

The script will:

1. Look up the latest AMI (Ubuntu 24.04 LTS  by default)
2. Launch a build instance with cloud-init user-data
3. Wait for provisioning to complete (~10-15 minutes)
4. Stop the instance and create an AMI
5. Terminate the build instance
6. Save the AMI ID to `~/.maverick/ami.json`

#### Manage instances

```sh
maverick instance create      # Launch a new instance connected to the message queue
maverick instance start       # Start a stopped instance
maverick instance stop        # Stop a running instance
maverick instance status      # Show instance details
maverick instance terminate   # Terminate Ec2 Instance
```

#### Compute instance commands

Worker output is streamed to CloudWatch Logs at `/maverick/worker` with one stream per issue.

If you remote into a worker, you can run the following comands

```sh
maverick infra status        # Show resource ARNs
maverick infra destroy       # Tear down all resources
maverick worker status       # Show systemd service status
maverick worker uninstall    # Remove systemd service
maverick worker run-once     # Process one message (testing)
```


### GitHub webhook

In your GitHub repo: Settings → Webhooks → Add webhook:

- **Payload URL:** The Function URL printed by `maverick cloud init`
- **Content type:** `application/json`
- **Secret:** The value of `GITHUB_WEBHOOK_SECRET` in your Secrets Manager secret
- **Events:** Select "Issues"
