CREATE TABLE IF NOT EXISTS sf_trial_users (
 username TEXT PRIMARY KEY, fullname TEXT NOT NULL, email TEXT NOT NULL,
 salt TEXT NOT NULL, password_hash TEXT NOT NULL, created_at TEXT NOT NULL,
 role TEXT NOT NULL DEFAULT 'user' CHECK(role='user'),
 tier TEXT NOT NULL DEFAULT 'trial' CHECK(tier='trial')
);
CREATE TABLE IF NOT EXISTS sf_support_messages (
 id INTEGER PRIMARY KEY AUTOINCREMENT, thread TEXT NOT NULL, sender TEXT NOT NULL,
 text TEXT NOT NULL DEFAULT '', sent_at TEXT NOT NULL,
 image_data TEXT, image_thumb TEXT, client_id TEXT NOT NULL,
 UNIQUE(sender,client_id)
);
CREATE INDEX IF NOT EXISTS sf_support_thread ON sf_support_messages(thread,id);
