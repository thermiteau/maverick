
# Install Maverick CLI

Install the `maverick` CLI from wherever this plugin is loaded — marketplace cache or local dev checkout.

## Dispatch

Dispatch the **maverick** agent with task `install` and any user-provided arguments. The agent will follow the process below and return a structured result.

## Process

1. Locate the `install.sh` script in the same directory as this SKILL.md
2. Run `bash <path-to-install.sh>`
3. The script will install the CLI, update Claude permissions, and create the default system config at `~/.maverick/settings.json` if it doesn't already exist
4. Verify the installation by running `maverick --help`
5. Report the result to the user — success or failure with any error output
