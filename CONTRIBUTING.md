# Contributing

Thanks for your interest in GTIC Trading Bot! Bug reports, strategy ideas and pull requests are welcome.

## Development setup

See [Local development](README.md#local-development) in the README. In short:

```bash
docker compose -f docker-compose.dev.yml up -d db   # TimescaleDB
uv sync --extra backtest && uv run alembic upgrade head
uv run uvicorn app.main:app --reload                # backend  :8000
cd frontend && npm install && npm run dev           # frontend :5173
```

## Before opening a pull request

```bash
uv run ruff check .
uv run pytest -q
cd frontend && npm run build
```

CI runs the same checks (with a TimescaleDB service) on every PR.

## Guidelines

- **Safety first.** Changes touching order execution, Testnet/Live or risk guards need tests and a clear
  description of the behaviour change. Never weaken the Live-mode safeguards (`ENABLE_LIVE`, confirm modal,
  audit-log-before-send).
- **Strategies** are single files in `app/strategy/strategies/` that only read `Context` and return `Signal`s
  (no API/DB/I/O). Bump `version` when logic changes and update the methodology doc `<name>.md`
  (and `<name>.vi.md` if present). See [docs/05-Strategy-Dev-Guide.md](docs/05-Strategy-Dev-Guide.md).
- **UI text** is written in English and wrapped in `t("…")` (`frontend/src/lib/i18n.ts`); add the Vietnamese
  translation to `frontend/src/locales/vi/`.
- Don't hardcode symbols or parameters — read them from config/DB.
- Commit messages follow Conventional Commits (`feat:`, `fix:`, `docs:` …).

## Reporting bugs

Open an issue with steps to reproduce, the mode (Backtest/Paper/Testnet/Live), and relevant logs.
**Never paste API keys or secrets.** For security issues, see [SECURITY.md](SECURITY.md).
