# syntax=docker/dockerfile:1

# ---- Stage 1: build frontend → dist ----
FROM node:24-slim AS frontend-build
WORKDIR /build
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm install
COPY frontend/ ./
RUN npm run build

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

EXPOSE 8000
# Prod: chạy migration rồi serve (UI + API) trên 1 cổng 8000.
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
