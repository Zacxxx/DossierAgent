import { spawnSync } from "node:child_process";
import { mkdirSync, rmSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const currentDir = path.dirname(fileURLToPath(import.meta.url));
const repositoryRoot = path.resolve(currentDir, "../../../..");
const e2eStateDir =
  process.env.DOSSIERAGENT_E2E_STATE_DIR ??
  path.join(repositoryRoot, "test-results", "e2e-state");
const sqlitePath =
  process.env.DOSSIERAGENT_SQLITE_PATH ?? path.join(e2eStateDir, "dossieragent.db");
const storagePath = process.env.DOSSIERAGENT_STORAGE_PATH ?? path.join(e2eStateDir, "storage");

export default async function globalSetup() {
  rmSync(e2eStateDir, { recursive: true, force: true });
  mkdirSync(e2eStateDir, { recursive: true });

  const result = spawnSync(
    "node",
    [
      "scripts/dossieragent.mjs",
      "seed",
      "--database-path",
      sqlitePath,
      "--storage-path",
      storagePath,
      "--reset",
    ],
    {
      cwd: repositoryRoot,
      env: {
        ...process.env,
        DOSSIERAGENT_SQLITE_PATH: sqlitePath,
        DOSSIERAGENT_STORAGE_PATH: storagePath,
      },
      stdio: "inherit",
    },
  );

  if (result.status !== 0) {
    throw new Error(`E2E seed failed with exit code ${result.status ?? 1}`);
  }
}
