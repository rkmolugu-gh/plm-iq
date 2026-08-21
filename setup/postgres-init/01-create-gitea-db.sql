-- Runs once on first PostgreSQL initialization (docker-entrypoint-initdb.d).
-- Gitea stores its metadata in its own database, separate from the plm-iq app DB.
CREATE DATABASE gitea;
