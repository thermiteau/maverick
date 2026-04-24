"""Tests for maverick.gh_app — bot-config loading (no network)."""

import json
from pathlib import Path

import pytest

from maverick import gh_app


class TestLoadBotConfig:
    def test_raises_when_config_missing(self, tmp_path: Path):
        with pytest.raises(gh_app.BotNotConfigured, match="no config"):
            gh_app.load_bot_config(path=tmp_path / "nope.json")

    def test_raises_when_malformed(self, tmp_path: Path):
        p = tmp_path / "config.json"
        p.write_text("{ not json")
        with pytest.raises(gh_app.BotNotConfigured, match="malformed"):
            gh_app.load_bot_config(path=p)

    def test_raises_when_no_bot_section(self, tmp_path: Path):
        p = tmp_path / "config.json"
        p.write_text(json.dumps({"other": {}}))
        with pytest.raises(gh_app.BotNotConfigured, match="no `bot` section"):
            gh_app.load_bot_config(path=p)

    def test_raises_when_missing_key(self, tmp_path: Path):
        p = tmp_path / "config.json"
        p.write_text(json.dumps({"bot": {"app_id": 1, "installation_id": 2}}))
        with pytest.raises(gh_app.BotNotConfigured, match="private_key_path"):
            gh_app.load_bot_config(path=p)

    def test_raises_when_pem_missing(self, tmp_path: Path):
        p = tmp_path / "config.json"
        p.write_text(
            json.dumps(
                {
                    "bot": {
                        "app_id": 1,
                        "installation_id": 2,
                        "private_key_path": str(tmp_path / "missing.pem"),
                    }
                }
            )
        )
        with pytest.raises(gh_app.BotNotConfigured, match="not found"):
            gh_app.load_bot_config(path=p)

    def test_loads_when_complete(self, tmp_path: Path):
        pem = tmp_path / "bot.pem"
        pem.write_text("-----BEGIN RSA PRIVATE KEY-----\nfake\n-----END RSA PRIVATE KEY-----")
        p = tmp_path / "config.json"
        p.write_text(
            json.dumps(
                {
                    "bot": {
                        "app_id": 123,
                        "installation_id": 456,
                        "private_key_path": str(pem),
                    }
                }
            )
        )
        cfg = gh_app.load_bot_config(path=p)
        assert cfg.app_id == 123
        assert cfg.installation_id == 456
        assert "BEGIN RSA PRIVATE KEY" in cfg.private_key


class TestCheckConfigured:
    def test_reports_unconfigured(self, monkeypatch, tmp_path: Path):
        monkeypatch.setattr(gh_app, "CONFIG_PATH", tmp_path / "missing.json")
        result = gh_app.check_configured()
        assert result["configured"] is False
        assert "no config" in result["reason"]


class TestSignJwt:
    """Regression coverage for the PyJWT-2.10 string-iss requirement.

    PyJWT raises 'Issuer (iss) must be a string' if you pass an int.
    The signer must coerce app_id to str before building the payload.
    """

    def test_iss_is_coerced_to_string(self, tmp_path: Path):
        # Generate a tiny RSA key just to satisfy PyJWT's signer.
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric import rsa

        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        pem = key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        ).decode()

        # Should not raise — int app_id must be coerced to str inside _sign_jwt.
        token = gh_app._sign_jwt(123456, pem)
        assert isinstance(token, str)
        assert token.count(".") == 2  # JWT shape: header.payload.sig

        # And the iss claim should be a string in the decoded payload.
        import jwt as pyjwt

        decoded = pyjwt.decode(token, options={"verify_signature": False})
        assert isinstance(decoded["iss"], str)
        assert decoded["iss"] == "123456"
