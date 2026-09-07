# Klaxon

Incident management desk with a SQLite-backed issue database, REST APIs, MCP tools, and a Slack slash-command agent.

Upstream systems and GitHub are **simulated** — ingest and agent actions are logged as side effects, not sent to real services.

## Quick start

```bash
cd /Users/alicabukel/Documents/GitHub/klaxon
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env

klaxon-seed          # sample code + data issues
klaxon-api           # http://127.0.0.1:3000  (docs at /docs)
```

```bash
pytest -q
```

## Layout

```
src/klaxon/
  db/          models, repository, conversation sessions
  api/         FastAPI REST + Slack route registration
  mcp/         FastMCP tool server (stdio)
  agent/       LangGraph agent + Slack session wrapper
  slack/       OAuth, signatures, commands, events (kiwipi-style)
  seed.py      sample incidents
manifest.yaml  Slack app definition
```

## REST API

| Method | Path | Purpose |
|--------|------|---------|
| `GET/POST` | `/v1/issues` | List / create |
| `GET/PATCH` | `/v1/issues/{public_id}` | Detail / update |
| `POST` | `/v1/issues/{public_id}/status` | Status transition |
| `GET/POST` | `/v1/issues/{public_id}/comments` | Comments |
| `GET` | `/v1/stats` | Counts by status / kind / severity / source |
| `POST` | `/v1/ingest` | Simulated upstream event |
| `GET` | `/v1/side-effects` | Simulated action log |
| `GET` | `/healthz` | Health |

No auth on the REST surface (local demo).

## MCP tools

```bash
klaxon-mcp    # stdio FastMCP server for Cursor / other agents
```

Tools: `search_issues`, `get_issue`, `issue_stats`, `create_issue`, `update_issue`, `update_issue_status`, `add_comment`, `simulate_upstream_ingest`, `create_github_issue`, `list_side_effects`.

The Slack agent uses the same tool surface in-process by default. Set `KLAXON_USE_MCP=1` to load tools via MCP stdio instead.

## Slack bot

Modeled on [kiwipi/slack-integration](https://github.com/ali-cabukel/kiwipi/tree/main/slack-integration): HTTP (not Socket Mode), OAuth install, HMAC verification, 3-second ack + background work.

### Commands

| Command | Purpose |
|---------|---------|
| `/klaxon <text>` | Talk to the incident agent (queries, creates, updates) |
| `/klaxon-reset` | End the current conversation for this user+channel |
| `/ping` | Liveness |

Follow-ups: another `/klaxon` within 30 minutes continues the same session; replies in the bot’s thread also continue it.

### Local Slack setup

1. Fill `.env` Slack credentials and generate secrets:

```bash
openssl rand -hex 32                                    # STATE_SECRET
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"  # TOKEN_ENCRYPTION_KEY
```

2. Run the API and expose it:

```bash
klaxon-api
ngrok http 127.0.0.1:3000
```

3. Set `PUBLIC_BASE_URL` to the ngrok HTTPS origin (no trailing slash). Create the Slack app from `manifest.yaml` (replace `YOUR-DOMAIN`). Visit `http://localhost:3000/slack/install`.

Without `ANTHROPIC_API_KEY`, the agent echoes so you can debug Slack plumbing first.

### Pitfalls (from kiwipi)

1. Ack within 3 seconds; do LLM/DB work after.
2. Verify signatures on raw body bytes.
3. Dedupe Slack event retries.
4. Ignore bot/self messages to avoid loops.
5. Tokens are per-workspace (`team_id`).
6. Slack uses mrkdwn, not Markdown.

## Data model

Issues have `kind` of `code` or `data`, with kind-specific fields in JSON `features`. Status audit rows, comments, labels, conversation history, and simulated side effects are stored alongside.

## License

Private / experimental.
