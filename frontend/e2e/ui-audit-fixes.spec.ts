import { expect, test, type Page } from "@playwright/test";

const agentId = "00000000-0000-4000-8000-000000000001";
const workflowId = "00000000-0000-4000-8000-000000000010";
const runId = "00000000-0000-4000-8000-000000000020";
const timestamp = "2026-10-08T08:00:00.000Z";
const agent = {
  id: agentId, name: "Reviewer", role: "Review", system_prompt: "Be precise",
  model: "claude-sonnet", temperature: 0.7, max_tokens: 4096, context_window: 128000,
  tools: [], created_at: timestamp, updated_at: timestamp,
};

async function mockApplication(page: Page) {
  const state = {
    config: {
      default_model: "claude-sonnet", temperature: 0.7, max_tokens: 4096,
      llm_provider_mode: "mock", code_executor_backend: "disabled",
      anthropic_key_configured: false, openai_key_configured: false, tavily_key_configured: false,
    },
    run: {
      id: runId, workflow_id: workflowId, workflow_title: "QA workflow",
      task: "Synthetic review", status: "AWAITING_CONFIRMATION", created_at: timestamp,
      total_tokens: 12, final_report: null as string | null,
      plan: { summary: "Review", steps: [{
        step_number: 1, agent_id: agentId, agent_name: "Reviewer", status: "PENDING",
        depends_on: [], subtask: "Review the change",
      }] },
    },
    exportFailure: false,
  };
  await page.route("**/api/v1/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const headers = { "access-control-allow-origin": "http://localhost:3000" };
    if (request.method() === "OPTIONS") return route.fulfill({ status: 204, headers: {
      ...headers, "access-control-allow-methods": "GET,POST,PATCH,PUT,OPTIONS",
      "access-control-allow-headers": "content-type",
    } });
    if (url.pathname.endsWith("/settings/config")) {
      if (request.method() === "PATCH") Object.assign(state.config, request.postDataJSON());
      return route.fulfill({ json: state.config, headers });
    }
    if (url.pathname.endsWith("/agents/models")) return route.fulfill({ headers, json: { items: [
      { key: "claude-sonnet", provider: "anthropic", tier: "balanced", context_window: 200000 },
      { key: "claude-haiku", provider: "anthropic", tier: "fast", context_window: 200000 },
    ] } });
    if (url.pathname.endsWith("/agents/tools")) return route.fulfill({ headers, json: { items: [] } });
    if (url.pathname.endsWith("/agents")) return route.fulfill({ headers, json: { items: [agent], total: 1 } });
    if (url.pathname.endsWith("/workflows")) return route.fulfill({ headers, json: { items: [{
      id: workflowId, title: "QA workflow", execution_type: "sequential", steps: [],
      graph_layout: {}, created_at: timestamp, updated_at: timestamp,
    }], total: 1 } });
    if (url.pathname.endsWith("/events")) return route.fulfill({ headers, contentType: "text/event-stream", body: `event: run:snapshot\ndata: ${JSON.stringify({ event: "run:snapshot", ts: timestamp, run_id: runId, data: {} })}\n\n` });
    if (url.pathname.endsWith("/export")) return route.fulfill(state.exportFailure
      ? { status: 503, headers, body: "Temporary failure" }
      : { headers: { ...headers, "content-disposition": `attachment; filename="run.${url.searchParams.get("format")}"` }, contentType: "text/plain", body: "QA result" });
    if (url.pathname.endsWith("/plan")) {
      state.run.plan.steps = request.postDataJSON().steps;
      return route.fulfill({ headers, json: state.run });
    }
    if (url.pathname.endsWith("/confirm")) state.run.status = "IN_PROGRESS";
    if (url.pathname.endsWith("/cancel")) state.run.status = "CANCELLED";
    return route.fulfill({ headers, json: state.run });
  });
  return state;
}

for (const theme of ["dark", "light"] as const) {
  test.describe(theme, () => {
    test.beforeEach(async ({ page }) => {
      await page.addInitScript((value) => localStorage.setItem("theme", value), theme);
    });

    test("saved defaults survive reload and populate a new agent", async ({ page }) => {
      await mockApplication(page);
      await page.goto("/settings");
      await expect(page.getByRole("combobox", { name: "Default model" })).toContainText("Claude Sonnet");
      await page.getByRole("combobox", { name: "Default model" }).click();
      await page.getByRole("option", { name: /Claude Haiku/ }).click();
      await page.getByLabel("Default temperature (0.0–1.0)").fill("0.3");
      await page.getByLabel("Default max tokens (1–8192)").fill("2048");
      await page.getByRole("button", { name: "Save changes" }).click();
      await expect(page.getByText("Settings saved successfully.")).toBeVisible();
      await page.reload();
      await expect(page.getByRole("combobox", { name: "Default model" })).toContainText("Claude Haiku");
      await expect(page.getByLabel("Default temperature (0.0–1.0)")).toHaveValue("0.3");
      await page.getByRole("button", { name: "Create Agent", exact: true }).click();
      await expect(page.getByRole("combobox", { name: "AI model", exact: true })).toContainText("Claude Haiku");
      await page.getByRole("button", { name: "Advanced Settings" }).click();
      await expect(page.getByRole("spinbutton", { name: "Max tokens", exact: true })).toHaveValue("2048");
    });

    test("dashboard selection is controlled and demo controls respond", async ({ page }) => {
      await mockApplication(page);
      const errors: string[] = [];
      page.on("console", (message) => { if (message.type() === "error") errors.push(message.text()); });
      await page.goto("/");
      await page.getByRole("combobox", { name: "Workflow", exact: true }).click();
      await page.getByRole("option", { name: "QA workflow" }).click();
      await expect(page.getByRole("combobox", { name: "Workflow", exact: true })).toContainText("QA workflow");
      await page.getByRole("button", { name: "Clear", exact: true }).click();
      await expect(page.getByText("Sample console cleared.")).toBeVisible();
      await expect(page.getByText("Cloned repository", { exact: false })).toHaveCount(0);
      await page.getByRole("button", { name: "More pipeline options" }).click();
      await expect(page.getByRole("button", { name: "Manage workflows" })).toBeVisible();
      await page.getByRole("button", { name: "Help about input context" }).click();
      await expect(page.getByText("Input context contains", { exact: false })).toBeVisible();
      expect(errors).toEqual([]);
    });

    test("Cancel in Plan preview cancels the saved run", async ({ page }) => {
      const state = await mockApplication(page);
      await page.goto("/");
      await page.getByRole("combobox", { name: "Workflow", exact: true }).click();
      await page.getByRole("option", { name: "QA workflow" }).click();
      await page.getByRole("button", { name: "Decompose and Run" }).click();
      await expect(page.getByRole("dialog", { name: "Plan preview" })).toBeVisible();
      await page.getByRole("button", { name: "Cancel", exact: true }).click();
      await expect(page.getByRole("dialog", { name: "Plan preview" })).toHaveCount(0);
      expect(state.run.status).toBe("CANCELLED");
    });

    test("existing unconfirmed run can be edited, confirmed, or cancelled", async ({ page }) => {
      const state = await mockApplication(page);
      await page.goto(`/runs/${runId}`);
      await page.getByRole("textbox", { name: "Task for Reviewer" }).fill("Edited from run details");
      await page.getByRole("button", { name: "Confirm and run" }).click();
      await expect(page.getByText("IN_PROGRESS", { exact: true })).toBeVisible();
      expect(state.run.plan.steps[0].subtask).toBe("Edited from run details");
      state.run.status = "AWAITING_CONFIRMATION";
      await page.reload();
      await page.getByRole("button", { name: "Cancel run" }).click();
      await expect(page.getByText("CANCELLED", { exact: true })).toBeVisible();
    });

    test("export failures are visible and downloads succeed after retry", async ({ page }) => {
      const state = await mockApplication(page);
      state.run.status = "COMPLETED";
      state.run.final_report = "QA result";
      state.exportFailure = true;
      const pageErrors: string[] = [];
      page.on("pageerror", (error) => pageErrors.push(error.message));
      await page.goto(`/runs/${runId}`);
      await page.getByRole("button", { name: "Download JSON" }).click();
      await expect(page.locator("main").getByRole("alert")).toHaveText("Export failed (503)");
      state.exportFailure = false;
      for (const format of ["JSON", "MD", "PDF"]) {
        const download = page.waitForEvent("download");
        await page.getByRole("button", { name: `Download ${format}` }).click();
        expect((await download).suggestedFilename()).toMatch(new RegExp(`\\.${format.toLowerCase()}$`));
      }
      expect(pageErrors).toEqual([]);
    });

    test("preset label follows the selected graph arrangement", async ({ page }) => {
      await mockApplication(page);
      await page.goto("/workflows");
      await page.getByRole("button", { name: "New workflow" }).click();
      await page.getByRole("button", { name: "Reviewer claude-sonnet" }).click();
      await page.getByRole("button", { name: "Reviewer claude-sonnet" }).click();
      const preset = page.getByRole("combobox", { name: "Arrange preset" });
      for (const label of ["Sequential chain", "Parallel + aggregator", "Hybrid graph"]) {
        await preset.click();
        await page.getByRole("option", { name: label, exact: true }).click();
        await expect(preset).toContainText(label);
      }
    });
  });
}
