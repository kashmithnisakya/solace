# Safety Policy

Solace talks with people who may be in pain, and some may be thinking about suicide.
These rules apply to every change. A pull request that weakens them will not be merged.

## Non-negotiable rules

1. **Every message is risk-screened before any other agent sees it.** The keyword screen always runs, even when the AI is down.
2. **Detectors can only raise risk, never lower it.** The most severe assessment wins.
3. **A person in crisis never sees an error.** If the AI fails during a crisis, a fixed message with crisis lines is sent.
4. **Crisis lines are shown from moderate risk upward**, and always in crisis mode.
5. **Crisis mode is sticky.** It stays on until the risk clearly drops, not just for one message.
6. **No method information.** Solace never gives details about methods, doses, or ways to self-harm.
7. **No diagnosis and no medication advice.**
8. **Faith is opt-in.** Solace only draws on the tradition the person picks, never preaches, and never frames suffering as punishment or weak faith.
9. **Honesty.** Solace says it is an AI whenever asked.

## Before any public launch

- [ ] Every crisis number in `solace/safety/hotlines.py` verified with the organisation
- [ ] Prompts and the crisis flow reviewed by a licensed mental-health professional
- [ ] Red-team evaluation of crisis conversations, including indirect and coded language
- [ ] Human counselor hand-off in place
- [ ] Privacy review: consent, encryption at rest, data deletion, and Sri Lanka's Personal Data Protection Act (No. 9 of 2022)

## Reporting a safety problem

If you find a conversation where Solace responds unsafely, please open an issue with the label `safety`,
removing any real personal information first. For sensitive reports, contact the maintainer privately.
