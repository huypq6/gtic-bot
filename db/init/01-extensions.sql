-- Runs ONCE when the Postgres container initializes (mounted into /docker-entrypoint-initdb.d).
-- Alembic does not manage extensions → enable them here. Hypertables are created in a migration (P1).
CREATE EXTENSION IF NOT EXISTS timescaledb;
