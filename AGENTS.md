# AGENTS.md

Guidance for coding agents (and humans) working in this repository.

## Project

Solace is an open-source AI companion for mental and emotional support. It talks with people who may be
in crisis, so **safety comes before features**. Read [SAFETY.md](SAFETY.md) before changing anything in
`solace/safety/`, `solace/assistants/`, or `solace/conversation.py`.

- Language: Python 3.12+, managed with [uv](https://docs.astral.sh/uv/)
- Web: FastAPI (`solace/api.py`) and a static Apple-style web app (`solace/web/`: `index.html`, `static/app.css`, `static/app.js`)
- Agents: OpenAI Agents SDK (`agents` package); key from `OPENAI_API_KEY` in `.env`
- Storage: SQLite (conversation history and issue graph)

## Commands

```bash
uv sync                                    # install
uv run uvicorn solace.api:app --reload     # run at http://localhost:8000
uv run pytest -q                           # tests
uv run ruff check . && uv run ruff format . # lint + format
```

Run tests and both ruff commands before every commit. CI runs the same checks.

## Layout

```
solace/
├── api.py               HTTP routes
├── conversation.py      per-message flow: risk screen → pick agent → reply + graph update
├── voice.py             Realtime voice: short-lived keys, spoken instructions
├── platform/            counsellor accounts, hand-off store, live broker, dashboard routes
├── knowledge/           knowledge search + citations; library/*.md are the notes
├── assessment.py        picks the next life area worth gently asking about
├── assistants/          agent definitions and prompts (companion, crisis, classifier, graph_builder)
├── graph/               issue graph models and SQLite store
├── safety/              keyword screen, risk levels, crisis lines
└── web/                 web app; no inline scripts or styles (the CSP blocks them)
tests/                   pytest suite; conftest.py has fakes for every LLM call
docs/ROADMAP.md          phases and status
```

## Safety rules (non-negotiable)

1. Every user message goes through `Conversation.assess` (keyword screen + LLM screener) **before** any agent replies.
2. Detectors may only **raise** risk. Never let one lower another (`safety.risk.combine`).
3. A crisis reply must never be an error: keep `fallback_crisis_message` working.
4. Never add method, dose, or self-harm instructions to any prompt, test, or doc.
5. No diagnosis, no medication advice, faith content only when the person opted in.
6. Changes to prompts or crisis flow need a test and should be flagged for professional review in the PR.
7. When you find a risky phrase the keyword screen misses, add it to `tests/test_screen.py`.
8. Voice follows the same rules: every user transcript goes through `/api/voice/turn` (`Conversation.voice_user`).
   Never give the browser the real API key; it only gets short-lived keys from `/api/voice/session`.
9. Knowledge notes are written in our own words with a working source `url`; never paste copyrighted text.
   Never add method or dose information. The Crisis agent never receives knowledge notes.
10. Counsellors may only see conversations the person consented to share (an open or past hand-off).
    Log every counsellor view and action with `PlatformStore.audit`, never message content.

## Code conventions

- Keep modules small and typed; Pydantic models for anything crossing a boundary.
- LLM calls are injected (`classify`, `respond`, `build_graph` in `Conversation`) so tests stay offline.
  **Tests must never call the network.** Use the fakes in `tests/conftest.py`.
- Agent output models must have all fields required (strict JSON schema).
- Line length 110; ruff decides formatting.
- Comments explain *why*, not *what*.

## UI conventions

- Follow Apple's Human Interface Guidelines: system font, 17px body, iOS system colours via CSS variables,
  translucent bars, sheets for secondary screens, 44px minimum touch targets.
- Every colour is a token in `:root` with a dark-mode value. Respect `prefers-reduced-motion`.
- Keep JS and CSS in `solace/web/static/`. Inline `<script>`/`<style>` and `style="…"` attributes are blocked by the CSP.
- Render model text with `textContent`, never `innerHTML`.

## Privacy

- Never commit real conversations, names, phone numbers or `.env`.
- The issue graph stores people by role ("mother", "best friend"), never by name.
- Anything stored about a person must be deletable through `DELETE /api/sessions/{id}`.
- Knowledge sources must be public domain or clearly licensed; keep the license next to the source.

## Git workflow

- `main` is protected: no direct pushes, no force pushes. Work on a branch (`feat/…`, `fix/…`, `docs/…`)
  and open a pull request. CI must pass before merging.
- Commit messages: short imperative subject line (≤ 72 chars), then a body explaining what and why.
- **Do not mention AI tools in commits or pull requests.** No AI co-author trailers
  (e.g. `Co-Authored-By:` lines for an AI), no "generated with …" footers, no AI names in titles or descriptions.
