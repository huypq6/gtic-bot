# Security Policy

GTIC Trading Bot can place orders with **real money**. Please read this before deploying it.

## Deployment model — no built-in authentication

GTIC is a **single-user, self-hosted** app. The web UI and REST/WebSocket API have **no login** and CORS
allows any origin. Anyone who can reach the port can view your account and **place, modify or close orders**.

- Never expose port `8000` to the public internet.
- Run it on localhost or a private network, or behind a VPN (Tailscale/WireGuard) or a reverse proxy
  with authentication (e.g. Caddy/nginx with basic auth or an SSO proxy).
- Restrict `CORS_ORIGINS` if you access it from a browser on another host.

## API keys

- Keys live only in `.env` (git-ignored) — never commit them.
- Live keys: enable **Futures + read only**, **disable withdrawals**, and **whitelist your server's IP**.
- Live trading is disabled unless `ENABLE_LIVE=1`, and each switch to LIVE requires typing `LIVE` to confirm.
- Every order (bot or manual) is written to the audit log **before** it is sent to the exchange.

## Supported versions

Only the latest commit on `main` receives fixes.

## Reporting a vulnerability

Please **do not open a public issue** for security problems. Use GitHub's
[private vulnerability reporting](https://github.com/huypq6/gtic-bot/security/advisories/new) instead.
Include steps to reproduce and the impact. You should get a response within a few days.
