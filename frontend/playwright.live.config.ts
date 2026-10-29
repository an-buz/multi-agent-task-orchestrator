import { tmpdir } from "node:os";
import path from "node:path";
import { defineConfig, devices } from "@playwright/test";

const baseURL = process.env.E2E_LIVE_BASE_URL;
const apiURL = process.env.E2E_LIVE_API_URL;

if (process.env.E2E_LIVE !== "true" || !baseURL || !apiURL) {
  throw new Error("Use make test-e2e-live to start the isolated mock-only stack.");
}

export default defineConfig({
  testDir: "./e2e-live",
  workers: 1,
  retries: 0,
  forbidOnly: true,
  timeout: 120_000,
  expect: { timeout: 20_000 },
  reporter: "list",
  outputDir: path.join(tmpdir(), "multi-agent-orchestrator-live-playwright"),
  use: {
    ...devices["Desktop Chrome"],
    baseURL,
    viewport: { width: 1600, height: 1000 },
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  webServer: {
    command: `node node_modules/next/dist/bin/next dev --hostname localhost --port ${new URL(baseURL).port}`,
    url: baseURL,
    reuseExistingServer: false,
    timeout: 180_000,
    gracefulShutdown: { signal: "SIGTERM", timeout: 5_000 },
    env: { E2E_LIVE: "true", DEMO_MODE: "false", NEXT_PUBLIC_API_URL: apiURL },
  },
});
