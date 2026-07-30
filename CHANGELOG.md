# Changelog

## 0.1.0 — 2026-07-30

- Initial Claude Code plugin: hooks for SessionStart/End, PostToolUse(+Failure), PreToolUse, UserPromptSubmit.
- Bridge maps Claude stdin JSON → `token-sentinel-adapter` `AdapterEvent`.
- Observe / alert / strict via userConfig + env.
- Node launcher bootstraps venv under `CLAUDE_PLUGIN_DATA` (monorepo editable or PyPI).
- SQLite-backed rehydrate for cross-process hook invocations.
- Skill `tokensentinel` for in-product help.
- Tests: bridge, host decisions, multi-agent isolation, hook_entry smoke.
