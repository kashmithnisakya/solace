# Demo GIF

`docs/demo.gif` (shown at the top of the README) is built from real screenshots of the app.
**Refresh it in the same PR whenever the UI changes.**

## Capture

Run the app (`uv run uvicorn solace.api:app`), open it in a browser at 375×812 (iPhone size) in light mode,
start from a fresh conversation, and take one screenshot per scene in `scenes.json`:

1. `01-welcome.jpg`: first visit, the welcome sheet
2. `02-chat.jpg`: "exams next month and i literally can't sleep. lying awake till 3am" and the reply
3. `03-sources.jpg`: "racing thoughts mostly. any ideas for the nights?", with the Sources chip in view
4. `04-care.jpg`: "honestly sometimes i think everyone would be better off without me", reply and care card
5. `05-map.jpg`: the map sheet
6. `06-voice.jpg`: a voice call, while Solace is speaking
7. `07-handoff.jpg`: Settings → Chat with a Counsellor, with a counsellor signed in to `/counsellor`
8. `08-counsellor.jpg`: after the counsellor accepts and replies, and the person answers

Save them in `frames/` with those names. The counsellor dashboard still (`counsellor-dashboard.jpg`) is the
same conversation in `/counsellor` at about 1200×760.

## Build

```bash
uv run --with pillow python scripts/make_demo_gif.py
```

Needs ffmpeg. Captions come from `scenes.json`; edit them there.
