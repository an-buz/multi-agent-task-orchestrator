import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import test from "node:test";

function contentSecurityPolicy(environment = {}) {
  const env = { ...process.env, NODE_ENV: "production", ...environment };

  if (!("NEXT_PUBLIC_API_URL" in environment)) delete env.NEXT_PUBLIC_API_URL;

  const rules = JSON.parse(
    execFileSync(
      process.execPath,
      [
        "--import",
        "./tests/register.mjs",
        "--input-type=module",
        "--eval",
        'import config from "./next.config.ts"; process.stdout.write(JSON.stringify(await config.headers()));',
      ],
      {
        cwd: fileURLToPath(new URL("..", import.meta.url)),
        env,
        encoding: "utf8",
        stdio: ["ignore", "pipe", "pipe"],
      },
    ),
  );

  assert.equal(rules[0].source, "/:path*");

  return rules[0].headers.find((header) => header.key === "Content-Security-Policy").value;
}

test("production CSP restricts resource origins, frames, objects, base and forms", () => {
  const policy = contentSecurityPolicy();

  for (const directive of [
    "default-src 'self'",
    "img-src 'self' data: blob:",
    "font-src 'self'",
    "connect-src 'self' http://localhost:8000",
    "object-src 'none'",
    "frame-src 'none'",
    "frame-ancestors 'none'",
    "base-uri 'self'",
    "form-action 'self'",
  ]) {
    assert.ok(policy.split("; ").includes(directive), directive);
  }

  assert.doesNotMatch(policy, /unsafe-eval|ws:|wss:|\*/);
  assert.match(policy, /script-src 'self' 'unsafe-inline'/);
  assert.match(policy, /style-src 'self' 'unsafe-inline'/);
});

test("CSP permits only the configured API origin, including its port", () => {
  const policy = contentSecurityPolicy({
    NEXT_PUBLIC_API_URL: "https://api.example.com:8443/api/v1?test=1",
  });

  assert.ok(policy.split("; ").includes("connect-src 'self' https://api.example.com:8443"));
  assert.doesNotMatch(policy, /localhost|api\/v1|test=1/);
});

test("relative API paths keep connections same-origin", () => {
  const policy = contentSecurityPolicy({ NEXT_PUBLIC_API_URL: "/api/v1" });

  assert.ok(policy.split("; ").includes("connect-src 'self'"));
});

test("only development CSP allows eval and local HMR sockets", () => {
  const policy = contentSecurityPolicy({ NODE_ENV: "development" });

  assert.match(policy, /script-src 'self' 'unsafe-inline' 'unsafe-eval'/);
  assert.ok(
    policy
      .split("; ")
      .includes("connect-src 'self' http://localhost:8000 ws://localhost:* ws://127.0.0.1:*"),
  );
  assert.ok(policy.split("; ").includes("img-src 'self' data: blob:"));
});

test("CSP rejects invalid API origins instead of interpolating configuration into directives", () => {
  for (const url of [
    "//evil.test/api",
    "https://user:secret@api.example.com",
    "data:text/plain,test",
    "https://api.example.com; img-src *",
    "https://api.example.com;img-src",
    "https://*.example.com",
  ]) {
    assert.throws(() => contentSecurityPolicy({ NEXT_PUBLIC_API_URL: url }));
  }
});

test("demo build artifacts and locks are isolated from the regular Next.js server", () => {
  const cwd = fileURLToPath(new URL("..", import.meta.url));

  function distDir(mode, live = "false") {
    const env = { ...process.env, E2E_LIVE: live };

    if (mode === undefined) delete env.DEMO_MODE;
    else env.DEMO_MODE = mode;

    return execFileSync(
      process.execPath,
      [
        "--import",
        "./tests/register.mjs",
        "--input-type=module",
        "--eval",
        'import config from "./next.config.ts"; process.stdout.write(config.distDir);',
      ],
      { cwd, env, encoding: "utf8" },
    );
  }

  assert.equal(distDir("true"), ".next/demo");
  assert.equal(distDir("false"), ".next");
  assert.equal(distDir(undefined), ".next");
  assert.equal(distDir("true", "true"), ".next/e2e-live");
  assert.equal(distDir("false", "true"), ".next/e2e-live");
});
