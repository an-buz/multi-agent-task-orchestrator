import { expect, test, type Page } from "@playwright/test";

const timestamp = "2026-10-15T10:00:00Z";
const uuid = (number: number) => `00000000-0000-4000-8000-${String(number).padStart(12, "0")}`;
const agents = Array.from({ length: 51 }, (_, index) => ({
  id: uuid(index + 1),
  name: `Agent ${index + 1}`,
  role: "Research",
  system_prompt: "Research",
  model: "claude-sonnet",
  temperature: 0.2,
  max_tokens: 2048,
  context_window: 128000,
  tools: [],
  created_at: timestamp,
  updated_at: timestamp,
}));
const workflows = Array.from({ length: 51 }, (_, index) => ({
  id: uuid(index + 101),
  title: `Workflow ${index + 1}`,
  execution_type: "parallel",
  steps: [1, 2].map((step) => ({
    step_number: step,
    agent_id: uuid(51),
    depends_on: [],
    input_transform: "",
  })),
  graph_layout: {},
  created_at: timestamp,
  updated_at: timestamp,
}));
const runs = Array.from({ length: 51 }, (_, index) => ({
  id: uuid(index + 201),
  workflow_id: uuid(151),
  workflow_title: "Workflow 51",
  task: `Task ${index + 1}`,
  status: "FAILED",
  created_at: timestamp,
  total_tokens: 0,
}));

async function setup(page: Page, theme: string) {
  const writes: Record<string, unknown>[] = [];
  const requests: string[] = [];
  await page.addInitScript((theme) => {
    localStorage.setItem("theme", theme);
    class Source extends EventTarget {
      close() {}
    }
    Object.defineProperty(window, "EventSource", { value: Source });
  }, theme);
  await page.route("**/api/v1/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname.replace("/api/v1", "");
    const headers = {
      "access-control-allow-origin": "http://localhost:3000",
      "access-control-allow-methods": "GET,POST,PUT,DELETE,OPTIONS",
      "access-control-allow-headers": "content-type",
    };
    if (request.method() === "OPTIONS") return route.fulfill({ status: 204, headers });
    requests.push(`${path}${url.search}`);
    if (
      (path === "/workflows" && request.method() === "POST") ||
      (path.startsWith("/workflows/") && request.method() === "PUT")
    ) {
      const values = request.postDataJSON() as Record<string, unknown>;
      writes.push(values);
      return route.fulfill({
        headers,
        json: { ...values, id: uuid(999), created_at: timestamp, updated_at: timestamp },
      });
    }
    const collection =
      path === "/agents"
        ? agents
        : path === "/workflows"
          ? workflows
          : path === "/runs"
            ? runs
            : null;
    if (collection) {
      const offset = Number(url.searchParams.get("offset") ?? 0);
      const limit = Number(url.searchParams.get("limit") ?? 50);
      return route.fulfill({
        headers,
        json: { items: collection.slice(offset, offset + limit), total: collection.length },
      });
    }
    if (path === `/runs/${runs[50].id}`)
      return route.fulfill({
        headers,
        json: {
          ...runs[50],
          plan: null,
          planning_error: {
            code: "planning_interrupted",
            message: "Planning was interrupted. Create a new run.",
          },
        },
      });
    if (path === "/agents/models" || path === "/agents/tools")
      return route.fulfill({ headers, json: { items: [] } });
    return route.fulfill({
      status: 404,
      headers,
      json: { error: { message: "Unknown fixture route" } },
    });
  });
  return { writes, requests };
}

for (const theme of ["light", "dark"]) {
  test(`catalogues include record 51 and independent workflows can be saved (${theme})`, async ({
    page,
  }) => {
    const { writes, requests } = await setup(page, theme);
    await page.goto("/agents");
    await page.getByPlaceholder("Search agents by name, role, or model…").fill("Agent 51");
    await expect(page.getByText("Agent 51", { exact: true }).first()).toBeVisible();
    await page.goto("/workflows");
    await page.getByRole("button", { name: "Edit Workflow 51", exact: true }).click();
    await expect(page.locator(".react-flow__node")).toHaveCount(2);
    await expect(page.locator(".react-flow__node").first()).toContainText("Agent 51");
    await expect(page.getByText("Graph is valid.")).toBeVisible();
    await page.getByRole("button", { name: "Save workflow" }).click();
    await expect.poll(() => writes.length).toBe(1);
    expect(writes[0].execution_type).toBe("parallel");
    await page.getByRole("button", { name: "New workflow" }).click();
    await page.getByPlaceholder("Workflow title").fill("Automatic input chain");
    const palette = page.getByRole("button", { name: "Agent 51 claude-sonnet", exact: true });
    await palette.click();
    await palette.click();
    await page.getByRole("combobox", { name: "Arrange preset" }).click();
    await page.getByRole("option", { name: "Sequential chain" }).click();
    await page.getByRole("button", { name: "Save workflow" }).click();
    await expect.poll(() => writes.length).toBe(2);
    expect(writes[1].steps).toEqual([
      { step_number: 1, agent_id: uuid(51), depends_on: [], input_transform: "" },
      { step_number: 2, agent_id: uuid(51), depends_on: [1], input_transform: "" },
    ]);
    expect(requests).toContain("/agents?limit=50&offset=50");
    expect(requests).toContain("/workflows?limit=50&offset=50");
    await page.goto("/");
    await page.getByRole("combobox", { name: "Workflow", exact: true }).click();
    await expect(page.getByRole("option", { name: "Workflow 51", exact: true })).toBeVisible();
  });

  test(`history reaches record 51 and planning errors survive reload (${theme})`, async ({
    page,
  }) => {
    await setup(page, theme);
    await page.goto("/runs");
    await expect(page.getByText("Task 1", { exact: true })).toBeVisible();
    await page.getByRole("button", { name: "Next page" }).click();
    await expect(page.getByText("Task 51", { exact: true })).toBeVisible();
    await expect(page.getByRole("button", { name: "Next page" })).toBeDisabled();
    await page.getByRole("button", { name: "Previous page" }).click();
    await expect(page.getByText("Task 1", { exact: true })).toBeVisible();
    await page.getByRole("button", { name: "Next page" }).click();
    await page.getByRole("link").filter({ hasText: "Task 51" }).click();
    for (let iteration = 0; iteration < 2; iteration++) {
      if (iteration) await page.reload();
      await expect(page.getByRole("alert").filter({ hasText: "Planning failed" })).toContainText(
        "Planning was interrupted. Create a new run.",
      );
      await expect(page.getByRole("link", { name: "Create new run" })).toHaveAttribute("href", "/");
      await expect(page.getByRole("button", { name: "Confirm and run" })).toHaveCount(0);
      await expect(page.getByRole("button", { name: "Retry step" })).toHaveCount(0);
    }
    await page.getByRole("link", { name: "Create new run" }).click();
    await expect(page.locator("#workflow-task")).toBeVisible();
  });
}
