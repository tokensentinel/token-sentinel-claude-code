"""Load plugin config from env + Claude userConfig env vars."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class PluginConfig:
    mode: str = "observe"
    project: str = "claude-code"
    cloud_endpoint: str | None = None
    api_key: str | None = None


def _env(*names: str, default: str = "") -> str:
    for n in names:
        v = os.environ.get(n)
        if v is not None and str(v).strip() != "":
            return str(v).strip()
    return default


def load_config() -> PluginConfig:
    # Claude plugin options: CLAUDE_PLUGIN_OPTION_<KEY> (key uppercased)
    mode = _env(
        "TOKENSENTINEL_MODE",
        "CLAUDE_PLUGIN_OPTION_MODE",
        default="observe",
    ).lower()
    if mode not in {"observe", "alert", "strict"}:
        mode = "observe"

    project = _env(
        "TOKENSENTINEL_PROJECT",
        "CLAUDE_PLUGIN_OPTION_PROJECT",
        default="claude-code",
    ) or "claude-code"

    endpoint = _env(
        "TOKENSENTINEL_CLOUD_ENDPOINT",
        "CLAUDE_PLUGIN_OPTION_CLOUD_ENDPOINT",
        default="",
    )
    api_key = _env(
        "TOKENSENTINEL_API_KEY",
        "CLAUDE_PLUGIN_OPTION_API_KEY",
        default="",
    )

    return PluginConfig(
        mode=mode,
        project=project,
        cloud_endpoint=endpoint or None,
        api_key=api_key or None,
    )
