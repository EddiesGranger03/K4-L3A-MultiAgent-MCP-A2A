from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

TEAM_KEY_PATTERN = re.compile(r"^sk-team-[A-Za-z0-9_-]{16,128}$")


@dataclass(frozen=True)
class Settings:
    competition_api_url: str
    team_api_key: str
    mcp_endpoint: str
    root: Path
    model_id: str | None
    model_base_url: str | None
    model_api_key: str | None

    @classmethod
    def load(cls, root: Path | None = None) -> Settings:
        resolved_root = (root or Path.cwd()).resolve()
        load_dotenv(resolved_root / ".env")
        api_url = os.getenv("COMPETITION_API_URL", "").strip().rstrip("/")
        team_key = os.getenv("COMPETITION_TEAM_API_KEY", "").strip()
        mcp_endpoint = os.getenv("MCP_ENDPOINT", "").strip()
        model_id = os.getenv("MODEL", "").strip()
        model_base_url = os.getenv("OPENROUTER_BASE_URL", "").strip().rstrip("/")
        model_api_key = os.getenv("OPENROUTER_API_KEY", "").strip()
        errors: list[str] = []
        if not api_url.startswith(("http://", "https://")):
            errors.append("COMPETITION_API_URL must be an absolute HTTP(S) URL")
        if not TEAM_KEY_PATTERN.fullmatch(team_key):
            errors.append("COMPETITION_TEAM_API_KEY must use the sk-team-... format")
        if not mcp_endpoint.startswith(("http://", "https://")):
            errors.append("MCP_ENDPOINT must be an absolute HTTP(S) URL")
        if any((model_id, model_base_url, model_api_key)):
            if not model_id:
                errors.append("MODEL is required when OpenRouter is configured")
            if not model_base_url.startswith("https://"):
                errors.append("OPENROUTER_BASE_URL must be an absolute HTTPS URL")
            if not model_api_key.startswith("sk-or-v1-"):
                errors.append("OPENROUTER_API_KEY must use the sk-or-v1-... format")
        if errors:
            raise ValueError("; ".join(errors))
        return cls(
            api_url,
            team_key,
            mcp_endpoint,
            resolved_root,
            model_id or None,
            model_base_url or None,
            model_api_key or None,
        )
