# token-sentinel-claude-code

**TokenSentinel for Claude Code** — stop coding agents from burning tokens on loops and thrash while the session is still running.

Works with:

- [`token-sentinel`](https://pypi.org/project/token-sentinel/) (rules engine)
- [`token-sentinel-adapter`](https://pypi.org/project/token-sentinel-adapter/) (host-agnostic kernel)

**Observe by default** (never blocks tools). Optional **strict** mode can deny tools after waste is detected.

Docs & product: [tokensentinel.dev](https://tokensentinel.dev)

## Status

**0.1.0** — Claude Code plugin with hooks for session and tool lifecycle. Cross-process state uses a local SQLite store under Claude’s plugin data directory.

## Install

### From this repository

```bash
git clone https://github.com/tokensentinel/token-sentinel-claude-code.git
cd token-sentinel-claude-code
claude --plugin-dir "$(pwd)"
```

On first session start, the plugin bootstraps a Python venv (under Claude plugin data) and installs runtime dependencies from PyPI (`token-sentinel`, `token-sentinel-adapter`).

### Local development

```bash
pip install -e ".[dev]"
# With local checkouts of the engine and adapter (optional):
# pip install -e /path/to/tokensentinel-sdk-python -e /path/to/tokensentinel-adapter -e ".[dev]"
pytest -q
claude --plugin-dir "$(pwd)"
```

Requires **Python 3.10+**, **Node.js** (hook launcher), and **Claude Code**.

## Configure

| Source | Keys |
|--------|------|
| Plugin settings (`userConfig`) | `mode`, `project`, `cloud_endpoint`, `api_key` |
| Environment | `TOKENSENTINEL_MODE`, `TOKENSENTINEL_PROJECT`, `TOKENSENTINEL_CLOUD_ENDPOINT`, `TOKENSENTINEL_API_KEY`, `TOKENSENTINEL_PYTHON` |

| Mode | Behavior |
|------|----------|
| `observe` (default) | Detect and annotate only |
| `alert` | Same local behavior; suitable when cloud alerting is enabled |
| `strict` | May **deny** tools on `PreToolUse` after waste is detected |

Cloud is **optional**. Leave `cloud_endpoint` / `api_key` empty for fully offline use.

## What it detects

- **tool_loop** — same tool with similar inputs repeating
- **retry_storm** — identical tool calls thrashing
- **retrieval_thrash** — Grep/search thrash
- **context pressure** — large tool outputs (estimated when token counts are missing)
- Multi-agent: windows are scoped per `agent_id` so sibling subagents do not false-trigger each other

## Fail-open

If Python or the runtime fails, hooks exit successfully and **do not block** Claude Code. When the runtime is degraded, you may see a short status message.

## License

Apache-2.0
