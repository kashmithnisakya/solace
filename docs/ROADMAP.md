# Roadmap

| Phase | Goal | Status |
|---|---|---|
| 0. Setup | Repo, license, structure, CI, Docker | ✅ Done |
| 1. Text MVP | Companion agent, risk screening, crisis mode, chat page | ✅ First version |
| 2. Assessment + issue graph | Gentle question flow (loosely guided by PHQ-9 / GAD-7); extract issues, emotions, triggers and supports into a graph; graph view | ✅ First version |
| 2.5 Human-like companion + Apple-style UI | Natural tone, streaming replies, onboarding, sheets, tap-to-call, history restore, security headers, rate limiting | ✅ First version |
| 3. Knowledge base (RAG) | Psychology (e.g. WHO mhGAP, self-help guides), opt-in faith sources (Buddhism, Hinduism, Islam, Christianity), general health info; citations on every answer | ✅ First version |
| 4. Real-time voice | OpenAI Realtime API over WebRTC, with the same safety screening | ✅ First version |
| 5. Platform | Counsellor accounts and dashboard, consented hand-off with live chat, audit log | ✅ First version |
| 6. Safety evaluation | Red-team suite (risk detection + judged replies), offline checks in CI, manual live workflow | ✅ First version |
| 7. Sinhala (then Tamil) | Prompts, keyword screen, translated sources, voice quality testing | Next |

## Issue graph (Phase 2)

- **Nodes:** issues (debt, loneliness, sleep, grief, exams), emotions, triggers, people, strengths and supports.
- **Edges:** causes, worsens, related to, helps with.
- A graph-builder agent updates the graph after each turn. The assessment agent looks for gaps and asks about them.
