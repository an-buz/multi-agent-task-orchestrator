import { expect, test } from "@playwright/test";

const timestamp = "2026-10-05T00:00:00.000Z";
const agents = [
  {
    id: "00000000-0000-4000-8000-000000000001",
    name: "Developer",
    role: "Implements the requested change.",
    system_prompt: "Implement the task.",
    model: "claude-sonnet",
    temperature: 0.2,
    max_tokens: 2048,
    context_window: 128000,
    tools: [],
    created_at: timestamp,
    updated_at: timestamp,
  },
  {
    id: "00000000-0000-4000-8000-000000000002",
    name: "Reviewer",
    role: "Reviews the implementation.",
    system_prompt: "Review the change.",
    model: "claude-sonnet",
    temperature: 0.2,
    max_tokens: 2048,
    context_window: 128000,
    tools: [],
    created_at: timestamp,
    updated_at: timestamp,
  },
];

type WorkflowResponse = {
  id: string;
  title: string;
  execution_type: "sequential" | "parallel" | "hybrid";
  steps: Array<{
    step_number: number;
    agent_id: string;
    depends_on: number[];
    input_transform: string;
  }>;
  graph_layout: Record<string, { x: number; y: number }>;
  created_at: string;
  updated_at: string;
};

test("creates and saves a connected sequential workflow", async ({ page }) => {
  page.on("request", (request) => {
    if (request.url().includes("api")) console.log("E2E API request", request.url());
  });
  let savedWorkflow: WorkflowResponse | undefined;
  await page.route("**/*", async (route) => {
    const requestUrl = new URL(route.request().url());
    console.log("E2E route", requestUrl.href);
    if (requestUrl.pathname === "/api/v1/agents") {
      await route.fulfill({ json: { items: agents, total: agents.length } });
      return;
    }

    if (requestUrl.pathname === "/api/v1/workflows") {
      if (route.request().method() === "POST") {
        const input = route.request().postDataJSON() as Omit<
          WorkflowResponse,
          "id" | "created_at" | "updated_at"
        >;
        savedWorkflow = {
          ...input,
          id: "00000000-0000-4000-8000-000000000010",
          created_at: timestamp,
          updated_at: timestamp,
        };
        await route.fulfill({ status: 201, json: savedWorkflow });
        return;
      }

      await route.fulfill({
        json: {
          items: savedWorkflow ? [savedWorkflow] : [],
          total: savedWorkflow ? 1 : 0,
        },
      });
      return;
    }

    await route.continue();
  });

  await page.goto("/workflows");
  await page.getByRole("button", { name: "New workflow" }).click();
  await page.getByPlaceholder("Workflow title").fill("Local E2E workflow");
  await page.getByRole("button", { name: "Developer claude-sonnet" }).click();
  await page.getByRole("button", { name: "Reviewer claude-sonnet" }).click();
  await page.getByLabel("Arrange preset").selectOption("sequential");

  await expect(page.locator(".react-flow__node")).toHaveCount(2);
  await expect(page.locator(".react-flow__edge-path")).toHaveCount(1);
  await expect(page.getByText("Graph is valid.")).toBeVisible();

  const node = page.locator(".react-flow__node-default").first();
  await expect(node).not.toHaveCSS("background-color", "rgb(255, 255, 255)");
  await expect(node).toHaveCSS("color", "rgb(230, 237, 245)");

  await page.getByRole("button", { name: "Save workflow" }).click();
  const workflowCard = page.locator("article").filter({ hasText: "Local E2E workflow" });
  await expect(workflowCard).toContainText("sequential");
  await expect(workflowCard).toContainText("2 steps");
  expect(savedWorkflow?.steps.map((step) => step.depends_on)).toEqual([[], [1]]);
});
