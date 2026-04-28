"""GitHub App authentication — mints installation access tokens.

The Maverick GitHub App (commonly installed as `maverick-bot`) is the identity
Maverick uses for the actions that must not appear as the human user:

- `gh pr review --approve` on PRs the agent-code-reviewer approved
- `gh pr merge --auto --squash` so auto-merge fires on the App's approval
- `maverick-state`, `maverick-lease`, `maverick-claim`, `maverick-dag`,
  `maverick-bprop` marker comments (so App-authored workflow state is
  visually distinct from human edits)

Configuration lives in `~/.maverick/config.json`:

    {
        "gh_app": {
            "app_id": 123456,
            "installation_id": 78901234,
            "private_key_path": "~/.maverick/maverick-gh-app.pem"
        }
    }

The legacy `bot` block name is still accepted for backward compatibility
(with a one-line stderr warning prompting migration); new installations
should use `gh_app`.

If the section is absent or the pem cannot be read, the helpers raise
GhAppNotConfigured. Callers should handle that as "fall back to the
human user" when the action doesn't actually need the App identity.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

CONFIG_PATH = Path("~/.maverick/config.json").expanduser()
TOKEN_TTL_SECONDS = 50 * 60  # tokens expire at 60 min; refresh at 50 to have headroom

# Config block names — `gh_app` is current, `bot` is the legacy alias.
GH_APP_KEY = "gh_app"
LEGACY_KEY = "bot"


class GhAppNotConfigured(RuntimeError):
    """Raised when the Maverick GitHub App is not configured or its key is unreadable."""


# Backward-compat alias. Existing callers (and `except` clauses in user
# code, if any) keep working. Remove once nothing imports it.
BotNotConfigured = GhAppNotConfigured


@dataclass
class GhAppConfig:
    app_id: int
    installation_id: int
    private_key: str


# Backward-compat alias for the dataclass name.
BotConfig = GhAppConfig


_cached_token: tuple[str, float] | None = None  # (token, expires_at_unix)


def load_gh_app_config(path: Path | None = None) -> GhAppConfig:
    """Read `~/.maverick/config.json` and return the GitHub App section."""
    if path is None:
        path = CONFIG_PATH
    if not path.exists():
        raise GhAppNotConfigured(f"no config at {path}")
    try:
        data = json.loads(path.read_text())
    except json.JSONDecodeError as e:
        raise GhAppNotConfigured(f"malformed config at {path}: {e}") from e

    block = data.get(GH_APP_KEY)
    used_legacy = False
    if not block:
        block = data.get(LEGACY_KEY)
        if block:
            used_legacy = True
            print(
                f"warning: {path} uses legacy `{LEGACY_KEY}` config block; "
                f"rename to `{GH_APP_KEY}` (the legacy name will stop being "
                "read in a future release)",
                file=sys.stderr,
            )
    if not block:
        raise GhAppNotConfigured(
            f"no `{GH_APP_KEY}` section in {path} — see "
            "`maverick gh-app status` for setup instructions"
        )

    for key in ("app_id", "installation_id", "private_key_path"):
        if key not in block:
            label = LEGACY_KEY if used_legacy else GH_APP_KEY
            raise GhAppNotConfigured(f"`{label}` config missing `{key}`")
    pem_path = Path(str(block["private_key_path"])).expanduser()
    if not pem_path.exists():
        raise GhAppNotConfigured(f"GitHub App private key not found at {pem_path}")
    try:
        pem = pem_path.read_text()
    except OSError as e:
        raise GhAppNotConfigured(f"cannot read GitHub App private key: {e}") from e
    return GhAppConfig(
        app_id=int(block["app_id"]),
        installation_id=int(block["installation_id"]),
        private_key=pem,
    )


# Backward-compat alias.
load_bot_config = load_gh_app_config


def _sign_jwt(app_id: int, private_key: str) -> str:
    """Sign a short-lived JWT identifying the App to GitHub.

    GitHub requires RS256. We use PyJWT; it pulls in cryptography.
    """
    try:
        import jwt
    except ImportError as e:
        raise GhAppNotConfigured(
            "PyJWT is required for GitHub App auth — install with `uv add pyjwt[crypto]`"
        ) from e
    now = int(time.time())
    payload = {
        "iat": now - 60,  # 60s clock skew tolerance
        "exp": now + 9 * 60,  # GitHub caps App JWTs at 10 min
        "iss": str(app_id),  # PyJWT >= 2.10 enforces RFC 7519 string-type for `iss`
    }
    return jwt.encode(payload, private_key, algorithm="RS256")


def mint_installation_token(cfg: GhAppConfig | None = None) -> str:
    """Return a fresh installation access token. Cached for ~50 min."""
    global _cached_token
    now = time.time()
    if _cached_token is not None and _cached_token[1] > now:
        return _cached_token[0]
    cfg = cfg or load_gh_app_config()
    app_jwt = _sign_jwt(cfg.app_id, cfg.private_key)
    result = subprocess.run(
        [
            "curl",
            "--fail",
            "--silent",
            "-X",
            "POST",
            "-H",
            f"Authorization: Bearer {app_jwt}",
            "-H",
            "Accept: application/vnd.github+json",
            f"https://api.github.com/app/installations/{cfg.installation_id}/access_tokens",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    data = json.loads(result.stdout)
    token = str(data["token"])
    _cached_token = (token, now + TOKEN_TTL_SECONDS)
    return token


def gh_app_env(base_env: dict[str, str] | None = None) -> dict[str, str]:
    """Return an env dict with GH_TOKEN set to the App's installation token.

    Pass to `subprocess.run(..., env=gh_app_env())` or to
    `gh_state.post_marker` to make the action appear as the Maverick GitHub
    App in GitHub's audit log.
    """
    env = dict(os.environ if base_env is None else base_env)
    env["GH_TOKEN"] = mint_installation_token()
    return env


# Backward-compat alias.
bot_env = gh_app_env


def gh_app_gh(*args: str) -> subprocess.CompletedProcess[str]:
    """Run `gh` as the Maverick GitHub App. Raises on non-zero exit."""
    return subprocess.run(
        ["gh", *args], capture_output=True, text=True, check=True, env=gh_app_env()
    )


# Backward-compat alias.
bot_gh = gh_app_gh


def check_configured() -> dict[str, Any]:
    """Diagnostic: returns a dict describing config state for `maverick gh-app status`."""
    try:
        cfg = load_gh_app_config()
    except GhAppNotConfigured as e:
        return {"configured": False, "reason": str(e)}
    try:
        mint_installation_token(cfg)
        return {"configured": True, "app_id": cfg.app_id, "installation_id": cfg.installation_id}
    except (subprocess.CalledProcessError, GhAppNotConfigured) as e:
        return {
            "configured": False,
            "reason": f"token mint failed: {e}",
            "app_id": cfg.app_id,
            "installation_id": cfg.installation_id,
        }
