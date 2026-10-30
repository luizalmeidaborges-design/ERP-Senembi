-- O gatilho de INSERT grava rev/updated_at com um UPDATE, que disparava o gatilho de UPDATE e trocava o
-- updated_at enviado pelo desktop pela hora do servidor. Agora o gatilho de UPDATE só age quando o rev
-- não mudou, ou seja, em alterações feitas pelo próprio ERP (que nunca gravam rev).
DROP TRIGGER IF EXISTS records_upd;
DROP TRIGGER IF EXISTS tasks_upd;
DROP TRIGGER IF EXISTS settings_upd;
CREATE TRIGGER records_upd AFTER UPDATE OF kind, code, name, due, status, payload, updated_at ON records
WHEN NEW.rev = OLD.rev BEGIN
    UPDATE sync_meta SET rev = rev + 1 WHERE id = 1;
    UPDATE records SET rev = (SELECT rev FROM sync_meta WHERE id = 1),
        updated_at = CASE WHEN NEW.updated_at = OLD.updated_at THEN CAST((julianday('now') - 2440587.5) * 86400000 AS INTEGER) ELSE NEW.updated_at END
        WHERE id = NEW.id;
END;
CREATE TRIGGER tasks_upd AFTER UPDATE OF project_id, title, due, status, updated_at ON tasks
WHEN NEW.rev = OLD.rev BEGIN
    UPDATE sync_meta SET rev = rev + 1 WHERE id = 1;
    UPDATE tasks SET rev = (SELECT rev FROM sync_meta WHERE id = 1),
        updated_at = CASE WHEN NEW.updated_at = OLD.updated_at THEN CAST((julianday('now') - 2440587.5) * 86400000 AS INTEGER) ELSE NEW.updated_at END
        WHERE id = NEW.id;
END;
CREATE TRIGGER settings_upd AFTER UPDATE OF value, updated_at ON settings
WHEN NEW.rev = OLD.rev BEGIN
    UPDATE sync_meta SET rev = rev + 1 WHERE id = 1;
    UPDATE settings SET rev = (SELECT rev FROM sync_meta WHERE id = 1),
        updated_at = CASE WHEN NEW.updated_at = OLD.updated_at THEN CAST((julianday('now') - 2440587.5) * 86400000 AS INTEGER) ELSE NEW.updated_at END
        WHERE key = NEW.key;
END;
