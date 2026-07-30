---
name: tokensentinel
description: TokenSentinel status and waste report for this Claude Code session. Use when the user asks about token waste, loops, or TokenSentinel mode.
---

# TokenSentinel

In-process FinOps for this coding session: detects tool loops, retry storms, and search thrash **while you work**.

## Modes

| Mode | Behavior |
|------|----------|
| `observe` (default) | Annotates waste; never blocks tools |
| `alert` | Same local behavior; stamps alert for optional cloud |
| `strict` | May **deny** tools after waste is detected (PreToolUse) |

Set via plugin userConfig or env: `TOKENSENTINEL_MODE=observe|alert|strict`.

## What it watches (v0.1)

- **tool_loop** — same tool + similar inputs repeating
- **retry_storm** — identical tool calls thrashing
- **retrieval_thrash** — Grep/search thrash
- **context pressure** — large tool outputs (estimated)
- Multi-agent: windows are **per agent_id** (siblings do not pool)

## Commands for the user

- Ask: "TokenSentinel status" — expect mode + that hooks are installed
- Ask: "What waste did you catch?" — summarize any systemMessages from this session
- To disable: turn off the **tokensentinel** plugin in `/plugin`

## Honesty

- Does not claim full LLM token invoices without host usage data
- Fail-open: if the runtime is down, Claude Code keeps working
- Cloud is optional (`cloud_endpoint` + `api_key`)
