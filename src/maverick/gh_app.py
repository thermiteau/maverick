"""GitHub App authentication — mints installation access tokens.

The `maverick-bot` GitHub App is the identity Maverick uses for the actions
that must not appear as the human user:

- `gh pr review --approve` on PRs the agent-code-reviewer approved
- `gh pr merge --auto --squash` so auto-merge fires on the bot's approval
- `maverick-state`, `maverick-lease`, `maverick-claim`, `maverick-dag`,
  `maverick-bprop` marker comments (so bot-authored workflow state is
  visually distinct from human edits)

Configuration lives in `~/.maverick/config.json`:

    {
        "bot": {
            "app_id": 123456,
            "installation_id": 78901234,
            "private_key_path": "~/.maverick/maverick-bot.pem"
        }
    }

If the `bot` section is absent or the pem cannot be read, the bot helpers
raise BotNotConfigured. Callers should handle that as "fall back to the
human user" when the action doesn't actually need the bot identity.
"""

from __future__ import annotations

import json
import os
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

CONFIG_PATH = Path("~/.maverick/config.json").expanduser()
TOKEN_TTL_SECONDS = 50 * 60  # tokens expire at 60 min; refresh at 50 to have headroom


class BotNotConfigured(RuntimeError):
    """Raised when the maverick-bot App is not configured or its key is unreadable."""


@dataclass
class BotConfig:
    app_id: int
    installation_id: int
    private_key: str


_cached_token: tuple[str, float] | None = None  # (token, expires_at_unix)


def load_bot_config(path: Path | None = None) -> BotConfig:
    """Read `~/.maverick/config.json` and return the bot section."""
    if path is None:
        path = CONFIG_PATH
    if not path.exists():
        raise BotNotConfigured(f"no config at {path}")
    try:
        data = json.loads(path.read_text())
    except json.JSONDecodeError as e:
        raise BotNotConfigured(f"malformed config at {path}: {e}") from e
    bot = data.get("bot")
    if not bot:
        raise BotNotConfigured(f"no `bot` section in {path}")
    for key in ("app_id", "installation_id", "private_key_path"):
        if key not in bot:
            raise BotNotConfigured(f"bot config missing `{key}`")
    pem_path = Path(str(bot["private_key_path"])).expanduser()
    if not pem_path.exists():
        raise BotNotConfigured(f"bot private key not found at {pem_path}")
    try:
        pem = pem_path.read_text()
    except OSError as e:
        raise BotNotConfigured(f"cannot read bot private key: {e}") from e
    return BotConfig(
        app_id=int(bot["app_id"]),
        installation_id=int(bot["installation_id"]),
        private_key=pem,
    )


def _sign_jwt(app_id: int, private_key: str) -> str:
    """Sign a short-lived JWT identifying the App to GitHub.

    GitHub requires RS256. We use PyJWT; it pulls in cryptography.
    """
    try:
        import jwt
    except ImportError as e:
        raise BotNotConfigured(
            "PyJWT is required for GitHub App auth — install with `uv add pyjwt[crypto]`"
        ) from e
    now = int(time.time())
    payload = {
        "iat": now - 60,  # 60s clock skew tolerance
        "exp": now + 9 * 60,  # GitHub caps App JWTs at 10 min
        "iss": app_id,
    }
    return jwt.encode(payload, private_key, algorithm="RS256")


def mint_installation_token(cfg: BotConfig | None = None) -> str:
    """Return a fresh installation access token. Cached for ~50 min."""
    global _cached_token
    now = time.time()
    if _cached_token is not None and _cached_token[1] > now:
        return _cached_token[0]
    cfg = cfg or load_bot_config()
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


def bot_env(base_env: dict[str, str] | None = None) -> dict[str, str]:
    """Return an env dict with GH_TOKEN set to the bot's installation token.

    Pass to `subprocess.run(..., env=bot_env())` or to `gh_state.post_marker`
    to make the action appear as `maverick-bot` in GitHub's audit log.
    """
    env = dict(os.environ if base_env is None else base_env)
    env["GH_TOKEN"] = mint_installation_token()
    return env


def bot_gh(*args: str) -> subprocess.CompletedProcess[str]:
    """Run `gh` as the bot. Returns the completed process; raises on non-zero."""
    return subprocess.run(
        ["gh", *args], capture_output=True, text=True, check=True, env=bot_env()
    )


def check_configured() -> dict[str, Any]:
    """Diagnostic: returns a dict describing bot-config state for `maverick bot status`."""
    try:
        cfg = load_bot_config()
    except BotNotConfigured as e:
        return {"configured": False, "reason": str(e)}
    try:
        mint_installation_token(cfg)
        return {"configured": True, "app_id": cfg.app_id, "installation_id": cfg.installation_id}
    except (subprocess.CalledProcessError, BotNotConfigured) as e:
        return {
            "configured": False,
            "reason": f"token mint failed: {e}",
            "app_id": cfg.app_id,
            "installation_id": cfg.installation_id,
        }
