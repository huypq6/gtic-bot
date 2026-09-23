# syntax=docker/dockerfile:1

# ---- Stage 1: build frontend → dist ----
FROM node:24-slim AS frontend-build
WORKDIR /build
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm install
COPY frontend/ ./
RUN npm run build

# ---- Stage 1b: đọc phiên bản từ git → VERSION.json (web hiện ở header) ----
# .git chỉ vào stage này; image cuối chỉ nhận file JSON. Không có .git → JSON rỗng (app ghi "dev").
FROM alpine:3.20 AS version
RUN apk add --no-cache git jq
WORKDIR /src
COPY .git ./.git
RUN git config --global --add safe.directory /src && \
    if git rev-parse HEAD >/dev/null 2>&1; then \
      jq -n --arg commit "$(git rev-parse --short HEAD)" \
            --arg build "$(git rev-list --count HEAD)" \
            --arg commit_date "$(git log -1 --format=%cI)" \
            --arg subject "$(git log -1 --format=%s)" \
            --arg built_at "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
            '$ARGS.named' > /VERSION.json; \
    else echo '{}' > /VERSION.json; fi

# ---- Stage 2: python runtime (uv) ----
FROM python:3.12-slim AS backend
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PATH="/app/.venv/bin:$PATH"

# Cài deps trước (tận dụng cache layer); không cài dev/backtest cho prod.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project --extra backtest

# Mã nguồn backend + migration
COPY app ./app
COPY alembic ./alembic
COPY alembic.ini ./

# Frontend đã build → FastAPI serve static tại "/"
COPY --from=frontend-build /build/dist ./frontend/dist
COPY --from=version /VERSION.json ./VERSION.json

EXPOSE 8000
# Prod: chạy migration rồi serve (UI + API) trên 1 cổng 8000.
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
