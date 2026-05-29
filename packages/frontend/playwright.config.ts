import path from "node:path";
import { fileURLToPath } from "node:url";

import { defineConfig, devices } from "@playwright/test";

const packageRoot = path.dirname(fileURLToPath(import.meta.url));
const repositoryRoot = path.resolve(packageRoot, "../..");
const e2eStateDir =
  process.env.DOSSIERAGENT_E2E_STATE_DIR ??
  path.join(repositoryRoot, "test-results", "e2e-state");
const apiPort = process.env.DOSSIERAGENT_E2E_API_PORT ?? "8111";
const frontendPort = process.env.DOSSIERAGENT_E2E_FRONTEND_PORT ?? "5174";
const sqlitePath =
  process.env.DOSSIERAGENT_SQLITE_PATH ?? path.join(e2eStateDir, "dossieragent.db");
const storagePath = process.env.DOSSIERAGENT_STORAGE_PATH ?? path.join(e2eStateDir, "storage");

const e2eEnv = {
  ...process.env,
  DOSSIERAGENT_SQLITE_PATH: sqlitePath,
  DOSSIERAGENT_STORAGE_PATH: storagePath,
};

export default defineConfig({
  testDir: "./tests/e2e",
  timeout: 60_000,
  fullyParallel: false,
  retries: process.env.CI ? 1 : 0,
  reporter: [["list"]],
  globalSetup: "./tests/e2e/global-setup.ts",
  use: {
    baseURL: `http://127.0.0.1:${frontendPort}`,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  webServer: [
    {
      command: [
        "uv run --package dossieragent-core",
        "python -m dossieragent_core.api",
        `--host 127.0.0.1 --port ${apiPort}`,
      ].join(" "),
      cwd: repositoryRoot,
      env: e2eEnv,
      url: `http://127.0.0.1:${apiPort}/health`,
      reuseExistingServer: false,
      timeout: 60_000,
    },
    {
      command: "bun run dev",
      cwd: packageRoot,
      env: {
        ...e2eEnv,
        DOSSIERAGENT_API_PROXY_TARGET: `http://127.0.0.1:${apiPort}`,
        VITE_DEV_HOST: "127.0.0.1",
        VITE_DEV_PORT: frontendPort,
      },
      url: `http://127.0.0.1:${frontendPort}`,
      reuseExistingServer: false,
      timeout: 60_000,
    },
  ],
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
});
