# Safety Policy

Solace talks with people who may be in pain, and some may be thinking about suicide.
These rules apply to every change. A pull request that weakens them will not be merged.

## Non-negotiable rules

1. **Every message is risk-screened before any other agent sees it.** The keyword screen always runs, even when the AI is down. In voice calls, every finished transcript of the person's speech is screened the same way, and a high-risk result interrupts the current spoken reply and switches to crisis mode.
2. **Detectors can only raise risk, never lower it.** The most severe assessment wins.
3. **A person in crisis never sees an error.** If the AI fails during a crisis, a fixed message with crisis lines is sent.
4. **Crisis lines are shown from moderate risk upward**, and always in crisis mode.
5. **Crisis mode is sticky.** It stays on until the risk clearly drops, not just for one message.
6. **No method information.** Solace never gives details about methods, doses, or ways to self-harm.
7. **No diagnosis and no medication advice.**
8. **Faith is opt-in.** Solace only draws on the tradition the person picks, never preaches, and never frames suffering as punishment or weak faith.
9. **Honesty.** Solace says it is an AI whenever asked.
10. **A human only joins with consent.** Counsellors can only open conversations the person chose to share, every view and action is audit-logged (never message content), and risk screening and crisis lines keep working while a counsellor is in the chat.

## Before any public launch

- [ ] Every crisis number in `solace/safety/hotlines.py` verified with the organisation
- [ ] Prompts and the crisis flow reviewed by a licensed mental-health professional
- [x] Red-team evaluation of crisis conversations, including indirect and coded language (first version: `python -m evals`, [baseline](docs/safety/2026-11-26-baseline.md))
- [ ] The evaluation datasets reviewed and extended by a mental-health professional, and run before every release with a PASS
- [ ] Every note in `solace/knowledge/library/` reviewed for accuracy and safety by a professional (and faith notes by someone from that tradition)
- [ ] Sinhala reviewed by native speakers: interface text, crisis wording, keyword phrases, and how faith comes up in Sinhala replies
- [ ] Sinhala voice tested with real speech (transcription has no Sinhala language code; it auto-detects with a hint)
- [ ] Sinhala-speaking counsellors available for hand-off
- [x] Human counsellor hand-off in place (first version)
- [ ] Counsellors vetted, trained and supervised, with an agreed escalation process for imminent risk
- [ ] A staffing plan so requests are answered, and honest wording when no one is online
- [ ] Voice tested with real speech: crisis detection from transcripts, numbers read out clearly, interruptions
- [ ] Privacy review: consent, encryption at rest, data deletion, and Sri Lanka's Personal Data Protection Act (No. 9 of 2022)

## Reporting a safety problem

If you find a conversation where Solace responds unsafely, please open an issue with the label `safety`,
removing any real personal information first. For sensitive reports, contact the maintainer privately.
