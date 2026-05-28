ALTER TABLE dossier_snapshots
ADD COLUMN warnings_json TEXT NOT NULL DEFAULT '[]';
