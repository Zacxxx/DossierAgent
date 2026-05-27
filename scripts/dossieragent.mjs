#!/usr/bin/env node
import { existsSync, readFileSync, readdirSync, statSync } from "node:fs";
import { join, relative, resolve } from "node:path";
import { spawn, spawnSync } from "node:child_process";
import process from "node:process";

const rootDir = resolve(new URL("..", import.meta.url).pathname);

const packages = [
  {
    name: "frontend",
    kind: "node",
    importPrefix: null,
    concern: "Desktop command center UI",
  },
  {
    name: "agent",
    kind: "python",
    importPrefix: "dossieragent_agent",
    concern: "Supervised commands, runs, tools, and prompt contracts",
  },
  {
    name: "database",
    kind: "python",
    importPrefix: "dossieragent_database",
    concern: "SQLite schema, migrations, and repositories",
  },
  {
    name: "search_engine",
    kind: "python",
    importPrefix: "dossieragent_search_engine",
    concern: "Elasticsearch mappings, indexing, and hybrid search",
  },
  {
    name: "browser",
    kind: "python",
    importPrefix: "dossieragent_browser",
    concern: "Playwright extraction worker and source adapters",
  },
  {
    name: "schedule",
    kind: "python",
    importPrefix: "dossieragent_schedule",
    concern: "Cron-facing watch scheduling and due-run policy",
  },
  {
    name: "processing",
    kind: "python",
    importPrefix: "dossieragent_processing",
    concern: "Dossier, listing, and contact-packet processing",
  },
  {
    name: "mcp",
    kind: "python",
    importPrefix: "dossieragent_mcp",
    concern: "MCP configuration and Elastic Agent Builder integration",
  },
  {
    name: "core",
    kind: "python",
    importPrefix: "dossieragent_core",
    concern: "Minimal composition and orchestration layer",
  },
];

const runtimeServices = [
  {
    name: "api",
    packageName: "core",
    cwd: "packages/core",
    command: ["python3", "-m", "dossieragent_core.api"],
    readyWhen: ["packages/core/src/dossieragent_core/api.py"],
    pending: "FastAPI composition entrypoint has not been created yet.",
  },
  {
    name: "frontend",
    packageName: "frontend",
    cwd: "packages/frontend",
    command: [detectPackageManager(), "run", "dev"],
    readyWhen: ["packages/frontend/package.json"],
    packageScript: "dev",
    pending: "Frontend package script has not been created yet.",
  },
  {
    name: "browser-worker",
    packageName: "browser",
    cwd: "packages/browser",
    command: ["python3", "-m", "dossieragent_browser.worker"],
    readyWhen: ["packages/browser/src/dossieragent_browser/worker.py"],
    pending: "Playwright worker entrypoint has not been created yet.",
  },
  {
    name: "scheduler",
    packageName: "schedule",
    cwd: "packages/schedule",
    command: ["python3", "-m", "dossieragent_schedule.cron.runner"],
    readyWhen: ["packages/schedule/src/dossieragent_schedule/cron/runner.py"],
    pending: "Cron runner entrypoint has not been created yet.",
  },
];

const mode = process.argv[2] ?? "status";

switch (mode) {
  case "dev":
  case "start":
    runRoot(mode);
    break;
  case "status":
    printStatus();
    break;
  case "packages":
    printPackages();
    break;
  case "check":
    runChecks();
    break;
  default:
    console.error(`Unknown command: ${mode}`);
    console.error("Usage: dossieragent <dev|start|status|packages|check>");
    process.exit(2);
}

function detectPackageManager() {
  const execPath = process.env.npm_execpath ?? "";
  return execPath.includes("bun") ? "bun" : "npm";
}

function readJson(path) {
  return JSON.parse(readFileSync(join(rootDir, path), "utf8"));
}

function packageRoot(packageName) {
  return join(rootDir, "packages", packageName);
}

function packageExists(packageName) {
  return existsSync(packageRoot(packageName));
}

function fileExists(path) {
  return existsSync(join(rootDir, path));
}

function hasPackageScript(packageName, scriptName) {
  const pkgPath = join("packages", packageName, "package.json");
  if (!fileExists(pkgPath)) return false;
  const pkg = readJson(pkgPath);
  return Boolean(pkg.scripts?.[scriptName]);
}

function hasPackageDependency(packageName, dependencyName) {
  const pkgPath = join("packages", packageName, "package.json");
  if (!fileExists(pkgPath)) return false;
  const pkg = readJson(pkgPath);
  return Boolean(pkg.dependencies?.[dependencyName] || pkg.devDependencies?.[dependencyName]);
}

function serviceReadiness(service) {
  const missingFiles = service.readyWhen.filter((path) => !fileExists(path));
  if (missingFiles.length > 0) {
    return {
      ready: false,
      reason: `${service.pending} Missing: ${missingFiles.join(", ")}`,
    };
  }
  if (service.packageScript && !hasPackageScript(service.packageName, service.packageScript)) {
    return {
      ready: false,
      reason: `Missing ${service.packageName} package script: ${service.packageScript}`,
    };
  }
  if (service.dependency && !hasPackageDependency(service.packageName, service.dependency)) {
    return {
      ready: false,
      reason: service.pending,
    };
  }
  return { ready: true, reason: "ready" };
}

function runRoot(selectedMode) {
  printHeader(selectedMode);
  const statuses = runtimeServices.map((service) => ({
    service,
    readiness: serviceReadiness(service),
  }));
  const ready = statuses.filter((entry) => entry.readiness.ready);
  const pending = statuses.filter((entry) => !entry.readiness.ready);

  if (pending.length > 0) {
    console.log("Pending runtime services:");
    for (const { service, readiness } of pending) {
      console.log(`- ${service.name}: ${readiness.reason}`);
    }
    console.log("");
  }

  if (ready.length === 0) {
    console.log("No runnable services yet. Root command surface is installed and ready.");
    console.log("Next implementation step: create the core FastAPI entrypoint and frontend shell.");
    return;
  }

  console.log("Starting runtime services:");
  for (const { service } of ready) {
    console.log(`- ${service.name}: ${service.command.join(" ")} (${service.cwd})`);
  }
  console.log("");

  const children = ready.map(({ service }) => startService(service));

  const stop = () => {
    for (const child of children) {
      if (!child.killed) child.kill("SIGTERM");
    }
  };

  process.on("SIGINT", () => {
    stop();
    process.exit(130);
  });
  process.on("SIGTERM", () => {
    stop();
    process.exit(143);
  });
}

function startService(service) {
  const [command, ...args] = service.command;
  const child = spawn(command, args, {
    cwd: join(rootDir, service.cwd),
    env: {
      ...process.env,
      PYTHONPATH: pythonPathForService(service.packageName),
    },
    stdio: ["ignore", "pipe", "pipe"],
  });

  prefixStream(child.stdout, service.name);
  prefixStream(child.stderr, service.name);

  child.on("exit", (code, signal) => {
    const reason = signal ? `signal ${signal}` : `code ${code}`;
    console.log(`[${service.name}] exited with ${reason}`);
  });

  return child;
}

function pythonPathForService(packageName) {
  const ownSrc = join(rootDir, "packages", packageName, "src");
  const coreSrc = join(rootDir, "packages", "core", "src");
  const existing = process.env.PYTHONPATH ? [process.env.PYTHONPATH] : [];
  return [ownSrc, coreSrc, ...existing].join(":");
}

function prefixStream(stream, label) {
  let buffer = "";
  stream.on("data", (chunk) => {
    buffer += chunk.toString();
    const lines = buffer.split(/\r?\n/);
    buffer = lines.pop() ?? "";
    for (const line of lines) {
      if (line.length > 0) console.log(`[${label}] ${line}`);
    }
  });
  stream.on("end", () => {
    if (buffer.length > 0) console.log(`[${label}] ${buffer}`);
  });
}

function printStatus() {
  printHeader("status");
  printPackages();
  console.log("");
  console.log("Runtime services:");
  for (const service of runtimeServices) {
    const readiness = serviceReadiness(service);
    const marker = readiness.ready ? "ready" : "pending";
    console.log(`- ${service.name} (${service.packageName}): ${marker}`);
    if (!readiness.ready) console.log(`  ${readiness.reason}`);
  }
}

function printPackages() {
  console.log("Packages:");
  for (const pkg of packages) {
    const marker = packageExists(pkg.name) ? "ok" : "missing";
    console.log(`- ${pkg.name}: ${marker} - ${pkg.concern}`);
  }
}

function printHeader(selectedMode) {
  console.log("DossierAgent root launcher");
  console.log(`mode: ${selectedMode}`);
  console.log(`root: ${rootDir}`);
  console.log("");
}

function runChecks() {
  printHeader("check");
  const failures = [];

  for (const pkg of packages) {
    if (!packageExists(pkg.name)) {
      failures.push(`Missing package directory: packages/${pkg.name}`);
    }
  }

  const pythonPackages = packages.filter((pkg) => pkg.kind === "python");
  const compileResult = spawnSync(
    "python3",
    ["-m", "compileall", ...pythonPackages.map((pkg) => `packages/${pkg.name}/src`)],
    {
      cwd: rootDir,
      stdio: "inherit",
    },
  );
  if (compileResult.status !== 0) {
    failures.push("Python compile check failed.");
  }

  failures.push(...checkFeaturePackageImports());

  if (failures.length > 0) {
    console.error("");
    console.error("Checks failed:");
    for (const failure of failures) console.error(`- ${failure}`);
    process.exit(1);
  }

  console.log("");
  console.log("Checks passed.");
}

function checkFeaturePackageImports() {
  const failures = [];
  const prefixes = new Set(
    packages.filter((pkg) => pkg.importPrefix).map((pkg) => pkg.importPrefix),
  );

  for (const pkg of packages) {
    if (pkg.kind !== "python" || pkg.name === "core") continue;

    const sourceRoot = join(packageRoot(pkg.name), "src");
    for (const file of walkFiles(sourceRoot, ".py")) {
      const text = readFileSync(file, "utf8");
      const importMatches = text.matchAll(/^\s*(?:from|import)\s+(dossieragent_[a-z_]+)/gm);
      for (const match of importMatches) {
        const importedPrefix = match[1];
        if (prefixes.has(importedPrefix) && importedPrefix !== pkg.importPrefix) {
          failures.push(
            `${relative(rootDir, file)} imports ${importedPrefix}; feature packages must not depend on each other.`,
          );
        }
      }
    }
  }

  return failures;
}

function walkFiles(dir, extension) {
  if (!existsSync(dir)) return [];

  const results = [];
  for (const entry of readdirSync(dir)) {
    const path = join(dir, entry);
    const stat = statSync(path);
    if (stat.isDirectory()) {
      if (entry === "__pycache__") continue;
      results.push(...walkFiles(path, extension));
    } else if (path.endsWith(extension)) {
      results.push(path);
    }
  }
  return results;
}
