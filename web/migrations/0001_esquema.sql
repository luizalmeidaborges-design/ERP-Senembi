-- Mesmo esquema criado por core.Store no app desktop (senembi.db).
CREATE TABLE IF NOT EXISTS records (
    id INTEGER PRIMARY KEY, kind TEXT NOT NULL, code TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL, due TEXT NOT NULL DEFAULT '', status TEXT NOT NULL DEFAULT '',
    payload TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS idx_records_kind_due ON records(kind,due);
CREATE TABLE IF NOT EXISTS counters (kind TEXT PRIMARY KEY, last_value INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS tasks (
    id INTEGER PRIMARY KEY, project_id INTEGER NOT NULL REFERENCES records(id) ON DELETE CASCADE,
    title TEXT NOT NULL, due TEXT NOT NULL DEFAULT '', status TEXT NOT NULL DEFAULT 'A fazer');
