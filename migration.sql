-- Existing users/messages schema from the supplied Worker. Run ONCE.
-- Backup D1 first. Do not rerun ALTER TABLE statements after successful migration.
ALTER TABLE users ADD COLUMN email TEXT NOT NULL DEFAULT '';
ALTER TABLE messages ADD COLUMN image_data TEXT;
ALTER TABLE messages ADD COLUMN image_thumb TEXT;
ALTER TABLE messages ADD COLUMN client_id TEXT;
ALTER TABLE messages ADD COLUMN notify_email INTEGER NOT NULL DEFAULT 0;
CREATE UNIQUE INDEX IF NOT EXISTS support_message_idempotency ON messages(sender,client_id);
CREATE INDEX IF NOT EXISTS support_message_recipient ON messages(recipient,id);
CREATE TABLE IF NOT EXISTS support_sessions (
 username TEXT NOT NULL, session_id TEXT NOT NULL, sequence INTEGER NOT NULL,
 last_seen_at TEXT NOT NULL, PRIMARY KEY(username,session_id)
);
CREATE TABLE IF NOT EXISTS support_reads (
 username TEXT NOT NULL, peer TEXT NOT NULL, last_id INTEGER NOT NULL DEFAULT 0,
 PRIMARY KEY(username,peer)
);
CREATE TABLE IF NOT EXISTS support_rate (
 key TEXT PRIMARY KEY,hits INTEGER NOT NULL,bucket INTEGER NOT NULL
);

-- Existing history stays visible, but only messages arriving after migration
-- trigger the new notification system. Run together with this migration once.
INSERT OR IGNORE INTO support_reads(username,peer,last_id)
SELECT recipient,sender,MAX(id) FROM messages GROUP BY recipient,sender;
