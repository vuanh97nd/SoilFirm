-- Chạy migration này trước khi triển khai worker.js cập nhật.
CREATE TABLE IF NOT EXISTS device_logins (
    username TEXT PRIMARY KEY,
    device_id TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS welcome_accounts (
    username TEXT PRIMARY KEY,
    seen_at TEXT NOT NULL
);
