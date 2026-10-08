import { expect, test } from "@playwright/test";

const workflowId = "00000000-0000-4000-8000-000000000010";
const runId = "00000000-0000-4000-8000-000000000020";
const readyRun = {
  id: runId,
  workflow_id: workflowId,
  workflow_title: "Planner workflow",
  task: "Review the project",
  status: "AWAITING_CONFIRMATION",
  created_at: "2026-10-08T12:00:00Z",
  total_tokens: 28,
  plan: {
    summary: "Review API risks",
    steps: [
      {
        step_number: 1,
        agent_id: "00000000-0000-4000-8000-000000000001",
        agent_name: "Reviewer",
        depends_on: [],
        subtask: "Review the API contracts",
        status: "PENDING",
      },
    ],
  },
};

for (const theme of ["dark", "light"]) {
  for (const outcome of ["ready", "failed", "cancelled"] as const) {
    test(`planner ${outcome} in ${theme} theme`, async ({ page }) => {
      await page.addInitScript((value) => localStorage.setItem("theme", value), theme);
      let confirmed = false;
      let edited: Record<string, unknown> | undefined;
      await page.route("**/api/v1/**", async (route) => {
        const request = route.request();
        const pathname = new URL(request.url()).pathname;
        const headers = {
          "access-control-allow-origin": request.headers().origin ?? "http://localhost:3000",
          "access-control-allow-methods": "GET,POST,PATCH,OPTIONS",
          "access-control-allow-headers": "content-type",
        };
        if (request.method() === "OPTIONS") return route.fulfill({ status: 204, headers });
        if (pathname === "/api/v1/agents") {
          return route.fulfill({ json: { items: [], total: 0 }, headers });
        }
        if (pathname === "/api/v1/workflows") {
          return route.fulfill({
            json: {
              items: [
                {
                  id: workflowId,
                  title: "Planner workflow",
                  execution_type: "sequential",
                  steps: [],
                  graph_layout: {},
                  created_at: readyRun.created_at,
                  updated_at: readyRun.created_at,
                },
              ],
              total: 1,
            },
            headers,
          });
        }
        if (pathname === "/api/v1/runs" && request.method() === "POST") {
          return route.fulfill({
            status: 201,
            json: { ...readyRun, status: "PLANNING", plan: null },
            headers,
          });
        }
        const state =
          outcome === "failed"
            ? {
                ...readyRun,
                status: "FAILED",
                plan: null,
                planning_error: {
                  code: "invalid_plan",
                  message: "The planner returned an invalid plan.",
                },
              }
            : outcome === "cancelled"
              ? { ...readyRun, status: "CANCELLED", plan: null }
              : { ...readyRun, status: confirmed ? "IN_PROGRESS" : "AWAITING_CONFIRMATION" };
        if (pathname === `/api/v1/runs/${runId}/events`) {
          // No plan:ready event: the completed plan must be recovered from GET/snapshot.
          return route.fulfill({
            contentType: "text/event-stream",
            headers,
            body: `event: run:snapshot\ndata: ${JSON.stringify({ event: "run:snapshot", runId, data: { run: state } })}\n\n`,
          });
        }
        if (pathname === `/api/v1/runs/${runId}/plan`) {
          edited = request.postDataJSON() as Record<string, unknown>;
          return route.fulfill({ json: readyRun, headers });
        }
        if (pathname === `/api/v1/runs/${runId}/confirm`) {
          confirmed = true;
          return route.fulfill({ json: { ...readyRun, status: "IN_PROGRESS" }, headers });
        }
        if (pathname === `/api/v1/runs/${runId}`) return route.fulfill({ json: state, headers });
        return route.fulfill({ status: 404, json: { detail: "Not mocked" }, headers });
      });
      await Promise.all([
        page.waitForResponse(
          (response) =>
            new URL(response.url()).pathname === "/api/v1/workflows" && response.status() === 200,
        ),
        page.goto("/"),
      ]);
      await page.getByRole("combobox", { name: "Workflow" }).click();
      await page.getByRole("option", { name: "Planner workflow" }).click();
      await page.getByRole("button", { name: "Decompose and Run" }).click();
      if (outcome === "ready") {
        await expect(page.getByRole("heading", { name: "Plan preview" })).toBeVisible();
        expect(confirmed).toBe(false);
        await page.getByLabel("Task for Reviewer").fill("Human-approved review task");
        await page.getByRole("button", { name: "Confirm and run" }).click();
        await expect(page).toHaveURL(new RegExp(`/runs/${runId}`));
        expect(edited?.steps).toEqual([
          expect.objectContaining({ subtask: "Human-approved review task" }),
        ]);
      } else {
        await expect(page.getByRole("main").getByRole("alert")).toHaveText(
          outcome === "failed"
            ? "The planner returned an invalid plan."
            : "Planning was cancelled.",
        );
        await expect(page.getByRole("heading", { name: "Plan preview" })).toHaveCount(0);
        expect(confirmed).toBe(false);
      }
    });
  }
}
