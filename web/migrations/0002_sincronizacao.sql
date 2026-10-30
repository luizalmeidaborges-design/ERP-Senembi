-- Sincronização com o app desktop.
-- updated_at: hora da última alteração (ms, relógio de quem alterou) — decide o conflito (vale a mais recente).
-- rev: ordem das alterações no servidor — o desktop pede "tudo com rev maior que o último que recebi".
ALTER TABLE records ADD COLUMN updated_at INTEGER NOT NULL DEFAULT 0;
ALTER TABLE records ADD COLUMN rev INTEGER NOT NULL DEFAULT 0;
ALTER TABLE tasks ADD COLUMN updated_at INTEGER NOT NULL DEFAULT 0;
ALTER TABLE tasks ADD COLUMN rev INTEGER NOT NULL DEFAULT 0;
ALTER TABLE settings ADD COLUMN updated_at INTEGER NOT NULL DEFAULT 0;
ALTER TABLE settings ADD COLUMN rev INTEGER NOT NULL DEFAULT 0;
CREATE TABLE IF NOT EXISTS sync_meta (id INTEGER PRIMARY KEY CHECK (id = 1), rev INTEGER NOT NULL);
INSERT OR IGNORE INTO sync_meta VALUES (1, 0);
-- Exclusões, para que o outro lado também apague.
CREATE TABLE IF NOT EXISTS tombstones (tbl TEXT NOT NULL, id INTEGER NOT NULL, deleted_at INTEGER NOT NULL,
    rev INTEGER NOT NULL, PRIMARY KEY (tbl, id));
CREATE INDEX IF NOT EXISTS idx_records_rev ON records(rev);
CREATE INDEX IF NOT EXISTS idx_tasks_rev ON tasks(rev);
CREATE INDEX IF NOT EXISTS idx_tombstones_rev ON tombstones(rev);

-- Toda gravação recebe o próximo rev; quem não informou updated_at recebe a hora atual.
CREATE TRIGGER IF NOT EXISTS records_ins AFTER INSERT ON records BEGIN
    UPDATE sync_meta SET rev = rev + 1 WHERE id = 1;
    UPDATE records SET rev = (SELECT rev FROM sync_meta WHERE id = 1),
        updated_at = CASE WHEN NEW.updated_at = 0 THEN CAST((julianday('now') - 2440587.5) * 86400000 AS INTEGER) ELSE NEW.updated_at END
        WHERE id = NEW.id;
    DELETE FROM tombstones WHERE tbl = 'records' AND id = NEW.id;
END;
CREATE TRIGGER IF NOT EXISTS records_upd AFTER UPDATE OF kind, code, name, due, status, payload, updated_at ON records BEGIN
    UPDATE sync_meta SET rev = rev + 1 WHERE id = 1;
    UPDATE records SET rev = (SELECT rev FROM sync_meta WHERE id = 1),
        updated_at = CASE WHEN NEW.updated_at = OLD.updated_at THEN CAST((julianday('now') - 2440587.5) * 86400000 AS INTEGER) ELSE NEW.updated_at END
        WHERE id = NEW.id;
END;
CREATE TRIGGER IF NOT EXISTS records_del AFTER DELETE ON records BEGIN
    UPDATE sync_meta SET rev = rev + 1 WHERE id = 1;
    INSERT OR REPLACE INTO tombstones VALUES ('records', OLD.id,
        CAST((julianday('now') - 2440587.5) * 86400000 AS INTEGER), (SELECT rev FROM sync_meta WHERE id = 1));
END;
CREATE TRIGGER IF NOT EXISTS tasks_ins AFTER INSERT ON tasks BEGIN
    UPDATE sync_meta SET rev = rev + 1 WHERE id = 1;
    UPDATE tasks SET rev = (SELECT rev FROM sync_meta WHERE id = 1),
        updated_at = CASE WHEN NEW.updated_at = 0 THEN CAST((julianday('now') - 2440587.5) * 86400000 AS INTEGER) ELSE NEW.updated_at END
        WHERE id = NEW.id;
    DELETE FROM tombstones WHERE tbl = 'tasks' AND id = NEW.id;
END;
CREATE TRIGGER IF NOT EXISTS tasks_upd AFTER UPDATE OF project_id, title, due, status, updated_at ON tasks BEGIN
    UPDATE sync_meta SET rev = rev + 1 WHERE id = 1;
    UPDATE tasks SET rev = (SELECT rev FROM sync_meta WHERE id = 1),
        updated_at = CASE WHEN NEW.updated_at = OLD.updated_at THEN CAST((julianday('now') - 2440587.5) * 86400000 AS INTEGER) ELSE NEW.updated_at END
        WHERE id = NEW.id;
END;
CREATE TRIGGER IF NOT EXISTS tasks_del AFTER DELETE ON tasks BEGIN
    UPDATE sync_meta SET rev = rev + 1 WHERE id = 1;
    INSERT OR REPLACE INTO tombstones VALUES ('tasks', OLD.id,
        CAST((julianday('now') - 2440587.5) * 86400000 AS INTEGER), (SELECT rev FROM sync_meta WHERE id = 1));
END;
CREATE TRIGGER IF NOT EXISTS settings_ins AFTER INSERT ON settings BEGIN
    UPDATE sync_meta SET rev = rev + 1 WHERE id = 1;
    UPDATE settings SET rev = (SELECT rev FROM sync_meta WHERE id = 1),
        updated_at = CASE WHEN NEW.updated_at = 0 THEN CAST((julianday('now') - 2440587.5) * 86400000 AS INTEGER) ELSE NEW.updated_at END
        WHERE key = NEW.key;
END;
CREATE TRIGGER IF NOT EXISTS settings_upd AFTER UPDATE OF value, updated_at ON settings BEGIN
    UPDATE sync_meta SET rev = rev + 1 WHERE id = 1;
    UPDATE settings SET rev = (SELECT rev FROM sync_meta WHERE id = 1),
        updated_at = CASE WHEN NEW.updated_at = OLD.updated_at THEN CAST((julianday('now') - 2440587.5) * 86400000 AS INTEGER) ELSE NEW.updated_at END
        WHERE key = NEW.key;
END;
