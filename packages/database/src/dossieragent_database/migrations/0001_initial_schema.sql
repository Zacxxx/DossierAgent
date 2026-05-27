CREATE TABLE users (
  id TEXT PRIMARY KEY,
  email TEXT UNIQUE NOT NULL,
  password_hash TEXT NOT NULL,
  display_name TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE refresh_tokens (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL REFERENCES users(id),
  token_hash TEXT NOT NULL,
  expires_at TEXT NOT NULL,
  revoked_at TEXT,
  created_at TEXT NOT NULL
);

CREATE TABLE search_criteria (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL REFERENCES users(id),
  mode TEXT NOT NULL,
  cities_json TEXT NOT NULL,
  districts_json TEXT NOT NULL DEFAULT '[]',
  budget_min REAL,
  budget_max REAL,
  surface_min REAL,
  rooms_min REAL,
  languages_json TEXT NOT NULL DEFAULT '["fr"]',
  filters_json TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE market_watches (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL REFERENCES users(id),
  criteria_id TEXT NOT NULL REFERENCES search_criteria(id),
  name TEXT NOT NULL,
  status TEXT NOT NULL,
  frequency TEXT NOT NULL,
  next_run_at TEXT,
  last_run_at TEXT,
  source_config_json TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE listings (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL REFERENCES users(id),
  watch_id TEXT REFERENCES market_watches(id),
  source TEXT NOT NULL,
  source_url TEXT NOT NULL,
  canonical_url TEXT NOT NULL,
  canonical_url_hash TEXT NOT NULL,
  source_listing_id TEXT,
  title TEXT NOT NULL,
  description TEXT,
  city TEXT,
  district TEXT,
  postal_code TEXT,
  price REAL,
  currency TEXT DEFAULT 'EUR',
  surface REAL,
  rooms REAL,
  agency_name TEXT,
  contact_hint TEXT,
  composite_fingerprint TEXT NOT NULL,
  duplicate_of_listing_id TEXT,
  status TEXT NOT NULL,
  fit_score REAL,
  fit_level TEXT,
  risk_flags_json TEXT NOT NULL DEFAULT '[]',
  explanation_json TEXT NOT NULL DEFAULT '[]',
  raw_payload_json TEXT NOT NULL DEFAULT '{}',
  first_seen_at TEXT NOT NULL,
  last_seen_at TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE INDEX idx_listings_user_status ON listings(user_id, status);
CREATE INDEX idx_listings_canonical_hash ON listings(canonical_url_hash);
CREATE INDEX idx_listings_fingerprint ON listings(composite_fingerprint);
CREATE INDEX idx_listings_source_listing_id ON listings(source, source_listing_id);

CREATE TABLE dossier_documents (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL REFERENCES users(id),
  filename TEXT NOT NULL,
  storage_path TEXT NOT NULL,
  mime_type TEXT NOT NULL,
  file_size INTEGER NOT NULL,
  sha256 TEXT NOT NULL,
  declared_type TEXT,
  detected_type TEXT,
  detected_owner_type TEXT,
  page_count INTEGER,
  status TEXT NOT NULL,
  extracted_text_path TEXT,
  issues_json TEXT NOT NULL DEFAULT '[]',
  warnings_json TEXT NOT NULL DEFAULT '[]',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE dossier_snapshots (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL REFERENCES users(id),
  readiness_score REAL NOT NULL,
  can_contact INTEGER NOT NULL,
  can_send_full_dossier INTEGER NOT NULL,
  missing_documents_json TEXT NOT NULL DEFAULT '[]',
  valid_documents_json TEXT NOT NULL DEFAULT '[]',
  recommendations_json TEXT NOT NULL DEFAULT '[]',
  created_at TEXT NOT NULL
);

CREATE TABLE contact_packets (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL REFERENCES users(id),
  listing_id TEXT NOT NULL REFERENCES listings(id),
  language TEXT NOT NULL,
  tone TEXT NOT NULL,
  status TEXT NOT NULL,
  message_draft TEXT NOT NULL,
  questions_json TEXT NOT NULL DEFAULT '[]',
  dossier_summary_json TEXT NOT NULL DEFAULT '{}',
  used_at TEXT,
  used_channel TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE user_checks (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL REFERENCES users(id),
  type TEXT NOT NULL,
  resource_type TEXT NOT NULL,
  resource_id TEXT NOT NULL,
  title TEXT NOT NULL,
  summary TEXT NOT NULL,
  status TEXT NOT NULL,
  payload_json TEXT NOT NULL DEFAULT '{}',
  completed_with TEXT,
  completed_note TEXT,
  created_at TEXT NOT NULL,
  completed_at TEXT
);

CREATE TABLE notifications (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL REFERENCES users(id),
  type TEXT NOT NULL,
  title TEXT NOT NULL,
  body TEXT NOT NULL,
  resource_type TEXT,
  resource_id TEXT,
  read_at TEXT,
  created_at TEXT NOT NULL
);

CREATE TABLE agent_runs (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL REFERENCES users(id),
  watch_id TEXT REFERENCES market_watches(id),
  trigger_type TEXT NOT NULL,
  intent TEXT NOT NULL,
  status TEXT NOT NULL,
  current_step TEXT,
  summary_json TEXT NOT NULL DEFAULT '{}',
  error_json TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  completed_at TEXT
);

CREATE TABLE agent_events (
  id TEXT PRIMARY KEY,
  run_id TEXT NOT NULL REFERENCES agent_runs(id),
  user_id TEXT NOT NULL REFERENCES users(id),
  type TEXT NOT NULL,
  severity TEXT NOT NULL,
  message TEXT NOT NULL,
  payload_json TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL
);

CREATE INDEX idx_agent_events_run ON agent_events(run_id, created_at);

