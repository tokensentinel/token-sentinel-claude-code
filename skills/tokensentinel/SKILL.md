---
name: tokensentinel
description: TokenSentinel status and waste help for this Claude Code session. Use when the user asks about token waste, loops, or TokenSentinel mode/status.
---

# TokenSentinel

Detects tool loops, retry storms, and search thrash **while you work**. Observe by default (does not block tools unless mode is `strict`).

## Modes

| Mode | Behavior |
|------|----------|
| `observe` (default) | Annotates waste; never blocks tools |
| `alert` | Same local behavior; for optional cloud alerting |
| `strict` | May **deny** tools after waste is detected (`PreToolUse`) |

Set via plugin userConfig or env: `TOKENSENTINEL_MODE=observe|alert|strict`.

## Live status (do not invent)

When the user asks for **TokenSentinel status**, run a live probe and report the JSON fields honestly (do not invent health):

```bash
python3 -c "import tokensentinel_claude_code.health as h; print(h.probe_health().to_json())"
```

If the package is installed / on `PYTHONPATH`:

```bash
python3 -m tokensentinel_claude_code.health
```

Report at least: `status`, `mode`, `sdk_version`, `adapter_version`, `sessions_db_ok`, `errors`, `notes`.

Do **not** claim healthy unless the probe says so. If the probe fails, say status is unknown/down.

## What it watches (v0.1)

- **tool_loop** — same tool with similar inputs repeating
- **retry_storm** — identical tool calls thrashing
- **retrieval_thrash** — Grep/search thrash
- **context pressure** — large tool outputs (estimated)
- Multi-agent: windows are **per agent_id** (siblings do not pool)

## Other user asks

- "What waste did you catch?" — summarize TokenSentinel `systemMessage` lines from this session
- Disable: turn off the **tokensentinel** plugin in `/plugin`

## Honesty

- Does not claim full LLM token invoices without host usage data
- Fail-open: if the runtime is down, Claude Code keeps working
- This release uses **SQLite rehydrate across hook processes**, not a long-lived HTTP sidecar
- Cloud is optional (`cloud_endpoint` + `api_key`)
