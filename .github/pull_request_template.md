## What & why

<!-- What does this change and why? Link related issues. -->

## How was it tested?

- [ ] `uv run ruff check .` and `uv run pytest -q` pass
- [ ] `cd frontend && npm run build` passes
- [ ] Tried it in the app (Backtest / Paper) — screenshots for UI changes

## Checklist

- [ ] Touches order execution / Testnet / Live / risk guards → tests added and behaviour change described
- [ ] Strategy logic changed → `version` bumped and methodology doc (`.md` / `.vi.md`) updated
- [ ] New UI text wrapped in `t()` with a Vietnamese entry in `frontend/src/locales/vi/`
- [ ] No secrets, API keys or `.env` values included
