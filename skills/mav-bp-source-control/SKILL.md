---
name: mav-bp-source-control
description: Source control conventions for all projects. Covers the requirement for remote repositories, repository hygiene, .gitignore standards, and sensitive file protection. Applied as a foundational requirement for all projects.
---

# Source Control Standards

Ensure all projects use source control with a remote repository, maintain clean history, and protect sensitive files.

## Principles

1. **All projects must use source control** — git is the standard; no exceptions
2. **Remote repository is mandatory** — local-only git is a hard fail; code must be pushed to a remote
3. **Protect sensitive files** — credentials, secrets, and environment files must never be committed
4. **Maintain clean history** — no large binaries, no build artifacts, no generated files in the repository

## Remote Repository Requirement

**This is a HARD REQUIREMENT.** A project without a remote repository is not under source control in any meaningful sense. Local-only git provides no backup, no collaboration, and no CI/CD integration.

### Validation

Run the following check at the start of any workflow:

```bash
git remote -v
```

- If no remote is configured, **stop and flag this as a blocking issue**
- The remote must be reachable — a configured remote pointing to a deleted or inaccessible repository is also a failure
- Acceptable remotes: GitHub, GitLab, Bitbucket, Azure DevOps, or any hosted git service

### What to Do When No Remote Exists

1. **Do not proceed with implementation work** — source control is a prerequisite
2. Inform the user that a remote repository is required
3. Offer to help create one (e.g., `gh repo create`) if the user has the appropriate tooling
4. Only continue once `git remote -v` shows a valid remote

## Validation Checks

Before beginning work on any project, verify these source control fundamentals:

| Check                    | Command / Method                          | Pass Criteria                                |
| ------------------------ | ----------------------------------------- | -------------------------------------------- |
| Remote exists            | `git remote -v`                           | At least one remote with a valid URL         |
| `.gitignore` exists      | Check for `.gitignore` in repo root       | File exists and is non-empty                 |
| No secrets in repo       | Scan for `.env`, credentials, key files   | No sensitive files tracked in git            |
| Clean working state      | `git status`                              | Understood; no unexpected untracked files    |

## .gitignore Requirements

Every repository must have a `.gitignore` file at the root. It must cover the following categories:

### Required Categories

| Category              | Examples                                                            |
| --------------------- | ------------------------------------------------------------------- |
| Build output          | `dist/`, `build/`, `out/`, `target/`, `*.o`, `*.pyc`, `__pycache__/` |
| Dependencies          | `node_modules/`, `.venv/`, `vendor/`                                |
| Environment files     | `.env`, `.env.local`, `.env.*.local`                                |
| IDE files             | `.idea/`, `.vscode/` (except shared settings), `*.swp`, `*.swo`    |
| OS files              | `.DS_Store`, `Thumbs.db`, `desktop.ini`                            |
| Test/coverage output  | `coverage/`, `.nyc_output/`, `htmlcov/`, `.pytest_cache/`          |
| Logs                  | `*.log`, `logs/`                                                    |

### Guidance

- Start from a language-appropriate template (e.g., GitHub's `gitignore` templates)
- Add project-specific entries as needed
- Never use `.gitignore` as a substitute for not generating files in the first place — if a build step creates output, configure it to write outside the repo or to a gitignored directory
- Review `.gitignore` when adding new tools or frameworks to the project

## Sensitive File Protection

Secrets, credentials, and keys must never be committed to the repository. This is non-negotiable.

### Files That Must Never Be Committed

| File / Pattern              | Contains                          |
| --------------------------- | --------------------------------- |
| `.env`, `.env.*`            | Environment variables, secrets    |
| `credentials.json`          | Service account credentials       |
| `*.pem`, `*.key`            | Private keys                      |
| `*secret*`, `*token*`       | API tokens, secret keys           |
| `aws-credentials`, `~/.aws` | AWS access keys                   |
| `*.p12`, `*.pfx`            | Certificate bundles with keys     |

### Enforcement

- All patterns above must be in `.gitignore`
- If a secret has been committed historically, it must be rotated immediately — removing it from the repo is not sufficient
- Use environment variables or secret managers (AWS Secrets Manager, Vault, etc.) instead of files
- CI/CD pipelines should use secret injection, not checked-in credential files

### Detection

To check if secrets are currently tracked:

```bash
# Check for common secret file patterns in tracked files
git ls-files | grep -iE '\.env$|\.env\.|credentials|\.pem$|\.key$|secret|token'
```

If any results appear, investigate immediately.

## Repository Hygiene

### No Large Binaries

- Do not commit binary files larger than 1 MB — use Git LFS, an artifact store, or a CDN
- Exceptions: small icons, fonts, or test fixtures that are genuinely part of the source
- Common offenders: database dumps, compiled binaries, media files, ZIP archives

### No Build Artifacts

- `dist/`, `build/`, `out/`, compiled files, bundled assets — these are generated from source and must not be committed
- CI/CD pipelines produce artifacts; the repository stores source

### Empty Directories

- Git does not track empty directories — use `.gitkeep` files to preserve directory structure where needed
- Only use `.gitkeep` when the empty directory is meaningful (e.g., a required output directory)

### Repository Size

- Keep the repository lean — large repos slow cloning, CI, and developer onboarding
- Periodically audit with `git count-objects -vH` or similar tools
- If the repo has grown large due to historical mistakes, consider `git filter-repo` to clean history (with team coordination)

## Branching and Commit Conventions

For detailed branching strategy, commit message format, merge conflict handling, and branch lifecycle, refer to:

**mav-git-workflow**

This skill covers:
- Branch naming conventions (`<type>/<issue>-<desc>`)
- Protected branch (`main`)
- Conventional Commits format
- Merge and rebase strategies
- Branch cleanup after merge

## Detecting Source Control Issues

When auditing a project or starting work, flag these patterns:

| Pattern                                    | Issue                           | Fix                                                       |
| ------------------------------------------ | ------------------------------- | --------------------------------------------------------- |
| No remote configured                       | Local-only repo — hard fail     | Create remote repo and push                               |
| No `.gitignore` file                       | Nothing is excluded from tracking| Create `.gitignore` with required categories              |
| `.env` or credentials tracked in git       | Secrets exposed in history      | Remove from tracking, add to `.gitignore`, rotate secrets |
| `node_modules/` or `dist/` committed       | Build/dependency artifacts in repo| Remove from tracking, add to `.gitignore`                |
| Large binaries in repo (>1 MB)             | Bloated repository              | Move to Git LFS or external storage                       |
| No `.gitkeep` in required empty dirs       | Directory structure lost on clone| Add `.gitkeep` where needed                               |
| Sensitive file patterns missing from `.gitignore` | Future risk of secret commits | Add missing patterns to `.gitignore`                  |
| Remote URL points to deleted/moved repo    | Effectively no remote           | Update remote URL to valid repository                     |

<!-- maverick-plugin-version: 3.3.3 -->
