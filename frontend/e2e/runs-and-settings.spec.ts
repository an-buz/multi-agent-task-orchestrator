import { expect, test } from "@playwright/test";

const agentId = "00000000-0000-4000-8000-000000000001";
const workflowId = "00000000-0000-4000-8000-000000000010";
const runId = "00000000-0000-4000-8000-000000000020";
const timestamp = "2026-10-07T12:00:00.000Z";
const run = {
  id: runId,
  workflow_id: workflowId,
  workflow_title: "Demo workflow",
  task: "Review the project",
  status: "AWAITING_CONFIRMATION",
  created_at: timestamp,
  total_tokens: 0,
  plan: [
    {
      step_number: 1,
      agent_id: agentId,
      agent_name: "Developer",
      status: "PENDING",
      depends_on: [],
      input: "Review the project",
    },
  ],
};

test("creates a run, previews the plan, confirms it, and monitors it on Dashboard", async ({ page }) => {
  let confirmed = false;
  await page.route("**/api/v1/**", async (route) => {
    const url = new URL(route.request().url());
    const cors = { "access-control-allow-origin": "http://localhost:3000" };
    if (route.request().method() === "OPTIONS") {
      await route.fulfill({
        status: 204,
        headers: {
          ...cors,
          "access-control-allow-methods": "GET,POST,PUT,PATCH,DELETE,OPTIONS",
          "access-control-allow-headers": "content-type",
        },
      });
      return;
    }
    if (url.pathname === "/api/v1/agents")
      return route.fulfill({ json: { items: [], total: 0 }, headers: cors });
    if (url.pathname === "/api/v1/workflows")
      return route.fulfill({
        json: {
          items: [
            {
              id: workflowId,
              title: "Demo workflow",
              execution_type: "sequential",
              steps: [],
              graph_layout: {},
              created_at: timestamp,
              updated_at: timestamp,
            },
          ],
          total: 1,
        },
        headers: cors,
      });
    if (url.pathname === "/api/v1/runs" && route.request().method() === "POST")
      return route.fulfill({
        status: 201,
        json: { id: runId, status: "PLANNING", plan: null },
        headers: cors,
      });
    if (url.pathname === `/api/v1/runs/${runId}/plan`)
      return route.fulfill({ json: run, headers: cors });
    if (url.pathname === "/api/v1/runs" && route.request().method() === "GET")
      return route.fulfill({ json: { items: [], total: 0 }, headers: cors });
    if (url.pathname === `/api/v1/runs/${runId}/confirm`) {
      confirmed = true;
      return route.fulfill({ json: { ...run, status: "IN_PROGRESS" }, headers: cors });
    }
    if (url.pathname === `/api/v1/runs/${runId}/events`)
      return route.fulfill({
        status: 200,
        contentType: "text/event-stream",
        body:
          'event: plan:ready\ndata: {"event":"plan:ready","runId":"' +
          runId +
          '","ts":"' +
          timestamp +
          '","data":{}}\n\n',
        headers: cors,
      });
    if (url.pathname === `/api/v1/runs/${runId}`)
      return route.fulfill({
        json: { ...run, status: confirmed ? "IN_PROGRESS" : "AWAITING_CONFIRMATION" },
        headers: cors,
      });
    return route.fulfill({ status: 404, json: { detail: "Not mocked" }, headers: cors });
  });

  await page.goto("/");
  await page.getByRole("combobox", { name: "Workflow" }).click();
  await page.getByRole("option", { name: "Demo workflow" }).click();
  await page.getByRole("button", { name: /Decompose and Run/ }).click();
  await expect(page.getByRole("heading", { name: "Plan preview" })).toBeVisible();
  await page.getByRole("button", { name: "Confirm and run" }).click();
  await expect(page).toHaveURL(new RegExp(`\\?run=${runId}`));
  await expect(page.getByRole("heading", { name: "Orchestration Center" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Inspect step 1: Developer" })).toBeVisible();
});

test("saves default settings through the settings API", async ({ page }) => {
  let saved: Record<string, unknown> | undefined;
  await page.route("**/api/v1/**", async (route) => {
    const url = new URL(route.request().url());
    const cors = { "access-control-allow-origin": "http://localhost:3000" };
    if (route.request().method() === "OPTIONS") {
      await route.fulfill({
        status: 204,
        headers: {
          ...cors,
          "access-control-allow-methods": "GET,POST,PUT,PATCH,DELETE,OPTIONS",
          "access-control-allow-headers": "content-type",
        },
      });
      return;
    }
    if (url.pathname === "/api/v1/agents")
      return route.fulfill({ json: { items: [], total: 0 }, headers: cors });
    if (url.pathname === "/api/v1/agents/models")
      return route.fulfill({
        json: {
          items: [
            {
              key: "claude-sonnet",
              provider: "anthropic",
              model_id: "mock-sonnet",
              tier: "balanced",
              context_window: 128000,
            },
          ],
        },
        headers: cors,
      });
    if (url.pathname === "/api/v1/settings/config" && route.request().method() === "GET")
      return route.fulfill({
        json: {
          llm_provider_mode: "mock",
          code_executor_backend: "disabled",
          anthropic_key_configured: false,
          openai_key_configured: false,
          tavily_key_configured: false,
          default_model: "claude-sonnet", temperature: 0.7, max_tokens: 4096,
        },
        headers: cors,
      });
    if (url.pathname === "/api/v1/settings/config" && route.request().method() === "PATCH") {
      saved = route.request().postDataJSON() as Record<string, unknown>;
      return route.fulfill({
        json: {
          llm_provider_mode: "mock",
          code_executor_backend: "disabled",
          anthropic_key_configured: false,
          openai_key_configured: false,
          tavily_key_configured: false,
          ...saved,
        },
        headers: cors,
      });
    }
    return route.fulfill({ status: 404, json: { detail: "Not mocked" }, headers: cors });
  });
  await page.goto("/settings");
  await expect(page.getByRole("button", { name: "Save changes" })).toBeEnabled();
  await page.getByLabel("Default temperature (0.0–1.0)").fill("0.4");
  await page.getByRole("button", { name: "Save changes" }).click();
  await expect(page.getByText("Settings saved successfully.")).toBeVisible();
  expect(saved?.temperature).toBe(0.4);
});
