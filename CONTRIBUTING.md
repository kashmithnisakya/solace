# Contributing to Solace

Thank you for helping. Please read the [Safety Policy](SAFETY.md) first.

## Setup

```bash
uv sync
cp .env.example .env   # add your OPENAI_API_KEY
uv run pytest
```

## Guidelines

- Keep changes small and focused, and add tests.
- If you find a risky phrase the keyword screen misses, add it to `tests/test_screen.py`. That is one of the most valuable contributions you can make.
- Never commit real conversations or personal data. Use made-up examples.
- Knowledge sources must be public domain or clearly licensed for reuse. Include the license with the source.
- Run `uv run ruff check . && uv run ruff format .` before opening a pull request.

Mental-health professionals, religious scholars and translators (especially Sinhala and Tamil) are especially welcome.
