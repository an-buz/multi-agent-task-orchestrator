import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import test from "node:test";

test("demo build artifacts and locks are isolated from the regular Next.js server", () => {
  const cwd = fileURLToPath(new URL("..", import.meta.url));
  function distDir(mode) {
    const env = { ...process.env };
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
});
