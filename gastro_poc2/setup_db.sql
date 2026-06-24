-- Creates a dedicated role + database for the Gastro EMR app.
-- Run once as the postgres superuser:
--   & "C:\Program Files\PostgreSQL\17\bin\psql.exe" -U postgres -f setup_db.sql
-- (matches the POSTGRES_* values in .env)

CREATE ROLE gastro WITH LOGIN PASSWORD 'gastro';
CREATE DATABASE gastro OWNER gastro;
GRANT ALL PRIVILEGES ON DATABASE gastro TO gastro;
