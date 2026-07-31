# Changelog

## 0.1.0 — 2026-07-31

- Initial Claude Code plugin: hooks for SessionStart/End, PostToolUse(+Failure), PreToolUse, UserPromptSubmit.
- Bridge maps Claude stdin JSON → `token-sentinel-adapter` `AdapterEvent`.
- Observe / alert / strict via userConfig + env.
- Node launcher bootstraps venv under `CLAUDE_PLUGIN_DATA` (PyPI or local editable installs).
- **State path:** per-hook process + SQLite rehydrate (HTTP sidecar not in this release).
- **Fix:** rehydrate failures set `DEGRADED` and emit a visible reason (no silent empty history).
- Live health probe: `python3 -m tokensentinel_claude_code.health`.
- Skill `tokensentinel` documents live status probe (not invented health).
- Tests: bridge, host decisions, multi-agent isolation, rehydrate-degraded, cross-process retry_storm, health probe.
