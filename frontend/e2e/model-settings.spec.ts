import { expect, test, type Page } from "@playwright/test";

const timestamp = "2026-10-14T10:00:00Z";
const agentId = "00000000-0000-4000-8000-000000000001";
const runId = "00000000-0000-4000-8000-000000000002";

async function setup(page: Page, theme: string, options: { empty?: boolean; fail?: boolean } = {}) {
  const models = options.empty
    ? []
    : [
        {
          key: "claude-sonnet",
          model_id: "claude-sonnet-test",
          provider: "anthropic",
          tier: "balanced",
          context_window: 200000,
          max_output_tokens: 128000,
          enabled: true,
        },
        {
          key: "claude-haiku",
          model_id: "claude-haiku-test",
          provider: "anthropic",
          tier: "fast",
          context_window: 200000,
          max_output_tokens: 64000,
          enabled: true,
        },
        {
          key: "gpt-4o",
          model_id: "gpt-test",
          provider: "openai",
          tier: "balanced",
          context_window: 128000,
          max_output_tokens: 16384,
          enabled: true,
        },
      ];
  let agent = {
    id: agentId,
    name: "Model reviewer",
    role: "Review",
    system_prompt: "Be precise",
    model: "claude-sonnet",
    temperature: 0.2,
    max_tokens: 1024,
    context_window: 128000,
    tools: [],
    created_at: timestamp,
    updated_at: timestamp,
    available: true,
    requires_reconfiguration: false,
  };
  const run = {
    id: runId,
    workflow_id: agentId,
    workflow_title: "Model test",
    task: "Review",
    status: "PAUSED",
    total_tokens: 28,
    total_time_ms: 100,
    created_at: timestamp,
    final_report: null,
    plan: {
      summary: "Review",
      steps: [
        {
          step_number: 1,
          agent_id: agentId,
          agent_name: agent.name,
          model: "claude-sonnet",
          status: "COMPLETED",
          depends_on: [],
          output: "Preserved result",
          attempt: 1,
        },
        {
          step_number: 2,
          agent_id: agentId,
          agent_name: agent.name,
          model: "claude-sonnet",
          status: "PENDING",
          depends_on: [1],
          output: null,
          attempt: 0,
        },
      ],
    },
  };
  const requests: { switches: unknown[]; agents: unknown[] } = { switches: [], agents: [] };
  await page.addInitScript((theme) => {
    localStorage.setItem("theme", theme);
    class Source extends EventTarget {
      close() {}
    }
    Object.defineProperty(window, "EventSource", { value: Source });
  }, theme);
  await page.route("**/api/v1/**", async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname.replace("/api/v1", "");
    const headers = {
      "access-control-allow-origin": "http://localhost:3000",
      "access-control-allow-methods": "GET,POST,PUT,PATCH,OPTIONS",
      "access-control-allow-headers": "content-type",
    };
    if (request.method() === "OPTIONS") return route.fulfill({ status: 204, headers });
    if (path.startsWith("/settings/models/") && request.method() === "PATCH") {
      requests.switches.push(request.postDataJSON());
      if (options.fail)
        return route.fulfill({
          status: 500,
          headers,
          json: { error: { code: "test_failure", message: "Could not save model switch." } },
        });
      const model = models.find((item) => item.key === path.split("/").at(-1))!;
      model.enabled = request.postDataJSON().enabled;
      if (!model.enabled && agent.model === model.key)
        agent = { ...agent, available: false, requires_reconfiguration: true };
      return route.fulfill({ headers, json: { items: models } });
    }
    if (path === "/settings/models") return route.fulfill({ headers, json: { items: models } });
    if (path === "/agents/models")
      return route.fulfill({ headers, json: { items: models.filter((model) => model.enabled) } });
    if (path === "/agents/tools") return route.fulfill({ headers, json: { items: [] } });
    if (path === "/agents" && request.method() === "GET")
      return route.fulfill({ headers, json: { items: [agent], total: 1 } });
    if (path === `/agents/${agentId}` && request.method() === "PUT") {
      requests.agents.push(request.postDataJSON());
      agent = {
        ...agent,
        ...request.postDataJSON(),
        available: true,
        requires_reconfiguration: false,
      };
      return route.fulfill({ headers, json: agent });
    }
    if (path === "/settings/config")
      return route.fulfill({
        headers,
        json: { default_model: "claude-sonnet", temperature: 0.7, max_tokens: 4096 },
      });
    if (path === `/runs/${runId}/cancel`) {
      run.status = "CANCELLED";
      return route.fulfill({ headers, json: run });
    }
    if (path === `/runs/${runId}`) return route.fulfill({ headers, json: run });
    if (path === "/runs") return route.fulfill({ headers, json: { items: [run], total: 1 } });
    return route.fulfill({ headers, json: { items: [], total: 0 } });
  });
  return requests;
}

for (const theme of ["light", "dark"]) {
  test(`model switches persist and agent repair excludes disabled choices (${theme})`, async ({
    page,
  }) => {
    const requests = await setup(page, theme);
    await page.goto("/models");
    await expect(page.getByRole("heading", { name: "Anthropic provider" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "OpenAI provider" })).toBeVisible();
    const toggle = page.getByRole("switch", { name: "claude-sonnet-test" });
    await expect(toggle).toBeChecked();
    await toggle.focus();
    await page.keyboard.press("Space");
    await expect(toggle).not.toBeChecked();
    await page.reload();
    await expect(page.getByRole("switch", { name: "claude-sonnet-test" })).not.toBeChecked();
    await page.getByRole("link", { name: "Agents", exact: true }).click();
    await expect(page.getByText("UNAVAILABLE", { exact: true })).toBeVisible();
    await page.getByRole("button", { name: "Edit Model reviewer", exact: true }).click();
    await page.getByRole("combobox", { name: "AI model" }).click();
    await expect(page.getByRole("option", { name: /Claude Sonnet/ })).toHaveCount(0);
    await page.getByRole("option", { name: /Claude Haiku/ }).click();
    await page.getByRole("button", { name: /Save changes/i }).click();
    await expect(page.getByRole("dialog")).toHaveCount(0);
    await expect(page.getByText("UNAVAILABLE", { exact: true })).toHaveCount(0);
    expect(requests.switches).toEqual([{ enabled: false }]);
    expect(requests.agents).toMatchObject([{ model: "claude-haiku" }]);
  });

  test(`paused run explains reconfiguration and supports cancellation (${theme})`, async ({
    page,
  }) => {
    await setup(page, theme);
    await page.goto(`/runs/${runId}`);
    await expect(page.getByText("PAUSED", { exact: true })).toBeVisible();
    await expect(page.getByText("Waiting for agent reconfiguration")).toBeVisible();
    await expect(page.getByText("Preserved result", { exact: true })).toBeVisible();
    await page.getByRole("button", { name: "Cancel run" }).click();
    await expect(page.getByText("CANCELLED", { exact: true })).toBeVisible();
  });
}

test("no connected providers shows setup instructions", async ({ page }) => {
  await setup(page, "light", { empty: true });
  await page.goto("/models");
  await expect(page.getByText("No connected providers", { exact: true })).toBeVisible();
  await expect(page.getByRole("switch")).toHaveCount(0);
});

test("failed model update preserves the saved switch state", async ({ page }) => {
  await setup(page, "dark", { fail: true });
  await page.goto("/models");
  const toggle = page.getByRole("switch", { name: "claude-sonnet-test" });
  await toggle.click();
  await expect(page.getByText("Could not save model switch.", { exact: true })).toBeVisible();
  await expect(toggle).toBeChecked();
});
