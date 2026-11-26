# Solace

**An open-source AI companion that listens, helps people understand what they are going through, and connects them to real help.**

> ⚠️ Solace is an AI. It is **not** a therapist, doctor, or emergency service.
> If you are in danger right now, call your local emergency number.
> In Sri Lanka: **1926** (National Mental Health Helpline, 24/7) · **1333** (CCCline) · **119** (Emergency).
> Elsewhere: [findahelpline.com](https://findahelpline.com).

## What it does

- **Talks like a caring person, not a chatbot.** Replies stream in as they are written, match the person's tone and length, and remember the details they shared.
- **Feels like a native app.** A calm, Apple-style interface with light and dark mode, tap-to-call crisis lines, and a conversation that survives a page reload.
- **Checks every message for suicide and self-harm risk.** There are two independent checks: a fast keyword screen and an AI screener. Either one can raise the alarm.
- **Switches to crisis mode** when risk is high. It stays calm, asks about safety directly, and connects the person to crisis lines and real people. If the AI fails, a fixed safety message is sent instead, so a person in crisis never sees an error.
- **Builds a private map (issue graph)** of what the person is going through: issues, feelings, triggers, people and supports, and how they connect. It uses roles, never names.
- **Asks gentle questions to fill gaps** (when it started, sleep, support, daily life and more). These are loosely guided by PHQ-9 / GAD-7, one at a time, never like a form, and never during a crisis.
- **Lets the person delete everything** with one button.
- **Includes faith only if the person chooses it** (Buddhism, Hinduism, Islam, Christianity, or none).
- Never diagnoses, and never gives medication advice.

Read the [Safety Policy](SAFETY.md) before contributing.

## Quick start

```bash
git clone https://github.com/kashmithnisakya/solace.git
cd solace
cp .env.example .env        # add your OPENAI_API_KEY
uv sync
uv run uvicorn solace.api:app --reload
```

Open http://localhost:8000.

### Production notes

- Run behind HTTPS and a reverse proxy, with `uvicorn --proxy-headers` so rate limiting sees real client IPs.
- The built-in rate limit (20 messages/minute per client) is in memory. Use a shared store such as Redis when running several instances.
- Strict security headers are on by default (CSP, no framing, no referrer, `no-store` on API responses).
- Message content is never logged; only risk levels are.

With Docker: `docker compose up --build`.

## API

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/chat/stream` | Same request; replies as server-sent events: `start` → `delta`… → `done` |
| `GET` | `/api/sessions/{id}/messages` | Restore a conversation's messages |
| `POST` | `/api/chat` | `{"message": "...", "session_id": null, "faith": "buddhism"}` → reply, risk level, resources |
| `GET` | `/api/sessions/{id}/graph` | The person's issue graph, coverage, and next area to explore |
| `DELETE` | `/api/sessions/{id}` | Delete the conversation, graph and risk state |
| `GET` | `/api/resources` | Crisis lines for the configured region |
| `GET` | `/health` | Health check |

## How it works

```
message ─► keyword screen ─┐
         └► AI risk screener ┴─► highest risk wins
                                   │
                 high / imminent ──┼──► Crisis Support agent  (+ crisis lines, always)
                 none … moderate ──┴──► Companion agent       (+ crisis lines from moderate up)
                                              ▲ knows the graph + one gap to gently ask about
message ─► Graph Builder agent (in parallel) ─► issue graph (SQLite)
```

Built with Python, [FastAPI](https://fastapi.tiangolo.com) and the [OpenAI Agents SDK](https://openai.github.io/openai-agents-python/).

```
solace/
├── api.py              FastAPI app
├── conversation.py     safety-first routing between agents
├── assessment.py       picks the next area worth gently asking about
├── graph/              issue graph models and storage
├── config.py           settings from .env
├── assistants/         companion, crisis, risk-screener and graph-builder agents
├── safety/             keyword screen, risk levels, crisis lines
└── web/                Apple-style web app (index.html, static/app.css, static/app.js)
tests/                  unit tests, including crisis-phrase test cases
```

## Roadmap

See [docs/ROADMAP.md](docs/ROADMAP.md). Next up: a knowledge base (psychology, faith and health sources), real-time voice, a platform with human counselors, and Sinhala support.

## Development

```bash
uv run pytest
uv run ruff check . && uv run ruff format .
```

Contributions are very welcome, especially from mental-health professionals. See [CONTRIBUTING.md](CONTRIBUTING.md). Coding agents should follow [AGENTS.md](AGENTS.md).

## License

[MIT](LICENSE)
