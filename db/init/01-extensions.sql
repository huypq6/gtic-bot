-- Chạy MỘT LẦN khi container Postgres khởi tạo (mount vào /docker-entrypoint-initdb.d).
-- Alembic không tự lo extension → bật ở đây. Hypertable tạo trong migration (P1).
CREATE EXTENSION IF NOT EXISTS timescaledb;
