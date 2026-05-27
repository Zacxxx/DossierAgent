#!/usr/bin/env node
import { createServer } from "node:http";
import { readFileSync } from "node:fs";
import { join, resolve } from "node:path";

const packageRoot = resolve(new URL("../../", import.meta.url).pathname);
const host = process.env.FRONTEND_HOST ?? "127.0.0.1";
const port = Number(process.env.FRONTEND_PORT ?? "5173");
const indexHtml = readFileSync(join(packageRoot, "public", "index.html"), "utf8");

const server = createServer((request, response) => {
  const path = new URL(request.url ?? "/", `http://${request.headers.host}`).pathname;

  if (path === "/" || path === "/index.html") {
    response.writeHead(200, {
      "Content-Type": "text/html; charset=utf-8",
      "Cache-Control": "no-store",
    });
    response.end(indexHtml);
    return;
  }

  response.writeHead(404, {
    "Content-Type": "application/json; charset=utf-8",
  });
  response.end(JSON.stringify({ error: "not_found", path }));
});

server.listen(port, host, () => {
  console.log(`[frontend] listening on http://${host}:${port}`);
});

