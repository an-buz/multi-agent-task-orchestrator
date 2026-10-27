import { expect, test, type Page } from "@playwright/test";

const agentId = "00000000-0000-4000-8000-000000000001";
const runId = "00000000-0000-4000-8000-000000000020";
const timestamp = "2026-10-26T10:00:00Z";
const agent = {
  id: agentId,
  name: "Reviewer",
  role: "Review",
  system_prompt: "Review changes",
  model: "claude-sonnet",
  temperature: 0.7,
  max_tokens: 20000,
  context_window: 200000,
  tools: [],
  created_at: timestamp,
  updated_at: timestamp,
};
const models = [
  {
    key: "claude-sonnet",
    provider: "anthropic",
    model_id: "sonnet",
    tier: "balanced",
    context_window: 1000000,
    max_output_tokens: 128000,
  },
  {
    key: "gpt-4o",
    provider: "openai",
    model_id: "gpt-4o",
    tier: "balanced",
    context_window: 128000,
    max_output_tokens: 16384,
  },
];

async function mockSnapshotEvents(page: Page) {
  await page.addInitScript(() => {
    class Source extends EventTarget {
      forward = (incoming: Event) => {
        this.dispatchEvent(
          new MessageEvent("run:snapshot", {
            data: JSON.stringify({
              event: "run:snapshot",
              data: { run: (incoming as CustomEvent).detail },
            }),
          }),
        );
      };
      constructor() {
        super();
        window.addEventListener("review-snapshot", this.forward);
      }
      close() {
        window.removeEventListener("review-snapshot", this.forward);
      }
    }
    Object.defineProperty(window, "EventSource", { value: Source });
  });
}

for (const theme of ["dark", "light"]) {
  test.describe(`review fixes in ${theme}`, () => {
    test.beforeEach(async ({ page }) => {
      await page.addInitScript((value) => localStorage.setItem("theme", value), theme);
    });

    test("remote plan edits refresh clean fields and block conflicting local edits", async ({
      page,
    }) => {
      await mockSnapshotEvents(page);
      const run = {
        id: runId,
        workflow_title: "Review",
        task: "Review",
        status: "AWAITING_CONFIRMATION",
        total_tokens: 0,
        created_at: timestamp,
        plan: {
          summary: "Review",
          steps: [
            {
              step_number: 1,
              agent_id: agentId,
              agent_name: "Reviewer",
              subtask: "Original",
              depends_on: [],
              status: "PENDING",
            },
          ],
        },
      };
      const submitted: Record<string, unknown>[] = [];
      await page.route("**/api/v1/**", async (route) => {
        const request = route.request();
        const path = new URL(request.url()).pathname;
        const headers = {
          "access-control-allow-origin": request.headers().origin ?? "http://localhost:3000",
          "access-control-allow-methods": "GET,POST,PATCH,OPTIONS",
          "access-control-allow-headers": "content-type",
        };
        if (request.method() === "OPTIONS") return route.fulfill({ status: 204, headers });
        if (path.endsWith("/plan")) {
          const body = request.postDataJSON();
          submitted.push(body);
          run.plan.steps = body.steps;
        }
        if (path.endsWith("/confirm")) {
          submitted.push(request.postDataJSON());
          run.status = "IN_PROGRESS";
        }
        return route.fulfill({
          headers,
          json: path.includes(`/runs/${runId}`) ? run : { items: [], total: 0 },
        });
      });
      await page.goto(`/runs/${runId}`);
      const task = page.getByLabel("Task for Reviewer");
      await expect(task).toHaveValue("Original");
      run.plan.steps[0].subtask = "Remote update";
      await page.evaluate(
        (snapshot) =>
          window.dispatchEvent(new CustomEvent("review-snapshot", { detail: snapshot })),
        run,
      );
      await expect(task).toHaveValue("Remote update");
      await task.fill("Local draft");
      run.plan.steps[0].subtask = "New remote update";
      await page.evaluate(
        (snapshot) =>
          window.dispatchEvent(new CustomEvent("review-snapshot", { detail: snapshot })),
        run,
      );
      await expect(task).toHaveValue("Local draft");
      await expect(page.getByRole("button", { name: "Start run", exact: true })).toBeDisabled();
      expect(submitted).toHaveLength(0);
      await page.getByRole("button", { name: "Reload latest plan" }).click();
      await expect(task).toHaveValue("New remote update");
      await task.fill("Reviewed task");
      await page.getByRole("button", { name: "Start run", exact: true }).click();
      await expect(page.getByRole("dialog", { name: "Plan preview" })).toHaveCount(0);
      expect(submitted.map((body) => body.expected_subtasks)).toEqual([
        { 1: "New remote update" },
        { 1: "Reviewed task" },
      ]);
    });

    test("model switch clamps tokens and manual edits respect the output limit", async ({
      page,
    }) => {
      let writes = 0;
      await page.route("**/api/v1/**", async (route) => {
        const request = route.request();
        const path = new URL(request.url()).pathname;
        const headers = {
          "access-control-allow-origin": request.headers().origin ?? "http://localhost:3000",
        };
        if (request.method() === "PUT") writes++;
        return route.fulfill({
          headers,
          json: {
            items: path.endsWith("/models") ? models : path.endsWith("/agents") ? [agent] : [],
            total: 1,
          },
        });
      });
      await page.goto("/agents");
      await page.getByRole("button", { name: "Edit Reviewer", exact: true }).click();
      await page.getByRole("combobox", { name: "AI model" }).click();
      await page.getByRole("option", { name: /GPT-4o/ }).click();
      await page.getByRole("button", { name: "Advanced Settings" }).click();
      await expect(page.getByRole("spinbutton", { name: "Max tokens", exact: true })).toHaveValue(
        "16384",
      );
      await page.getByRole("spinbutton", { name: "Max tokens", exact: true }).fill("20000");
      await page.getByRole("button", { name: "Save Changes", exact: true }).click();
      await expect(page.getByText(/supports at most .* output tokens/)).toBeVisible();
      expect(writes).toBe(0);
    });

    test("saving workflow blocks Cancel, Escape and edits until the response arrives", async ({
      page,
    }) => {
      let releaseSave: (() => void) | undefined;
      let saveStarted = false;
      await page.route("**/api/v1/**", async (route) => {
        const request = route.request();
        const path = new URL(request.url()).pathname;
        const headers = {
          "access-control-allow-origin": request.headers().origin ?? "http://localhost:3000",
          "access-control-allow-methods": "GET,POST,OPTIONS",
          "access-control-allow-headers": "content-type",
        };
        if (request.method() === "OPTIONS") return route.fulfill({ status: 204, headers });
        if (path.endsWith("/workflows") && request.method() === "POST") {
          saveStarted = true;
          await new Promise<void>((resolve) => {
            releaseSave = resolve;
          });
          return route.fulfill({
            headers,
            json: {
              ...request.postDataJSON(),
              id: runId,
              created_at: timestamp,
              updated_at: timestamp,
            },
          });
        }
        return route.fulfill({
          headers,
          json: {
            items: path.endsWith("/agents") ? [agent] : [],
            total: path.endsWith("/agents") ? 1 : 0,
          },
        });
      });
      try {
        await page.goto("/workflows");
        await page.getByRole("button", { name: "New workflow", exact: true }).click();
        await page.getByPlaceholder("Workflow title").fill("Pending workflow");
        await page.getByRole("button", { name: "Reviewer claude-sonnet" }).click();
        await page.getByRole("button", { name: "Save workflow", exact: true }).click();
        await expect.poll(() => saveStarted).toBe(true);
        const dialog = page.getByRole("dialog", { name: "Workflow editor" });
        await expect(dialog.getByRole("button", { name: "Cancel", exact: true })).toBeDisabled();
        await expect(page.getByPlaceholder("Workflow title")).toBeDisabled();
        await expect(dialog.getByRole("button", { name: "Reviewer claude-sonnet" })).toBeDisabled();
        await page.keyboard.press("Escape");
        await expect(dialog).toBeVisible();
        releaseSave?.();
        await expect(dialog).toBeHidden();
      } finally {
        releaseSave?.();
      }
    });
  });
}
