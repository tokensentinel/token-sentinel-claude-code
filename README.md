# token-sentinel-claude-code

**TokenSentinel for Claude Code** — official host plugin for [Claude Code](https://code.claude.com).

Host bridge to [`token-sentinel-adapter`](https://pypi.org/project/token-sentinel-adapter/) / [`token-sentinel`](https://pypi.org/project/token-sentinel/).

Detects coding-agent waste (**tool loops**, **retry storms**, **search thrash**) mid-session.  
**Observe by default** (never blocks). Optional `strict` can deny tools via `PreToolUse`.

> Architecture: `plugin_architecture_v0.md` · UX: `plugin_ux_journey_v0.md` · hygiene: `release_hygiene_v0.md` (parent monorepo docs).

## Status

**0.1.0** — first hook bridge. In-process + SQLite rehydrate (disk path of Hybrid C). Long-lived HTTP sidecar can land later without changing this bridge contract.

## Install (local dev)

From a monorepo layout:

```text
TS/
  tokensentinel-sdk-python/
  tokensentinel-adapter/
  token-sentinel-claude-code/   ← this repo
```

```bash
cd token-sentinel-claude-code
pip install -e ../tokensentinel-sdk-python -e ../tokensentinel-adapter -e ".[dev]"
pytest -q
```

### Load into Claude Code

```bash
claude --plugin-dir /path/to/token-sentinel-claude-code
```

On `SessionStart`, `scripts/run_hook.js` creates a venv under `CLAUDE_PLUGIN_DATA` and installs requirements (editable siblings when present).

## Configure

| Source | Keys |
|--------|------|
| Plugin `userConfig` | `mode`, `project`, `cloud_endpoint`, `api_key` |
| Env overrides | `TOKENSENTINEL_MODE`, `TOKENSENTINEL_PROJECT`, `TOKENSENTINEL_CLOUD_ENDPOINT`, `TOKENSENTINEL_API_KEY`, `TOKENSENTINEL_PYTHON` |

Modes: `observe` (default) · `alert` · `strict`.

## Naming

| Layer | Name |
|-------|------|
| GitHub / folder | `token-sentinel-claude-code` |
| Claude plugin id | `tokensentinel` |
| PyPI (optional bridge package) | `token-sentinel-claude-code` |
| Display | TokenSentinel for Claude Code |

## Layout

```text
.claude-plugin/plugin.json   # manifest + userConfig
hooks/hooks.json             # SessionStart, PostToolUse, PreToolUse, …
scripts/run_hook.js          # node launcher + runtime bootstrap
scripts/hook_entry.py        # stdin → EngineHandle → stdout
tokensentinel_claude_code/   # bridge, config, host_decision, runtime
skills/tokensentinel/        # skill help text
tests/                       # fixtures + unit/integration
```

## Multi-agent

Hook payloads with `agent_id` / `agent_type` are forwarded to the adapter.  
Rule windows are **per `(session_id, agent_id)`** — sibling subagents do not pool into false `retry_storm` / `tool_loop` hits.

## Fail-open

If Python or the engine fails, hooks exit **0** with no deny. Claude Code keeps working. Degraded reasons may appear as `systemMessage` when available.

## License

Apache-2.0
