---
name: install
description: Install the maverick CLI tool system-wide from the plugin directory.
user-invocable: true
disable-model-invocation: true
---

# Install Maverick CLI

Install the `maverick` CLI from wherever this plugin is loaded — marketplace cache or local dev checkout.

## Process

1. Locate the `install.sh` script in the same directory as this SKILL.md
2. Run `bash <path-to-install.sh>`
3. Verify the installation by running `maverick --help`
4. Report the result to the user — success or failure with any error output
