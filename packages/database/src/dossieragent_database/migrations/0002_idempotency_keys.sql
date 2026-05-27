CREATE TABLE idempotency_keys (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL REFERENCES users(id),
  scope TEXT NOT NULL,
  idempotency_key TEXT NOT NULL,
  resource_type TEXT NOT NULL,
  resource_id TEXT NOT NULL,
  created_at TEXT NOT NULL,
  UNIQUE(user_id, scope, idempotency_key)
);

CREATE INDEX idx_idempotency_keys_lookup
  ON idempotency_keys(user_id, scope, idempotency_key);

