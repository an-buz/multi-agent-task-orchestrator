import { expect, test, type Page } from "@playwright/test";

const id = "00000000-0000-4000-8000-000000000020";
const agentId = "00000000-0000-4000-8000-000000000001";
const timestamp = "2026-10-14T10:00:00Z";

async function setup(page: Page, status: string) {
  const run = {
    id,
    workflow_id: agentId,
    workflow_title: "Probe workflow",
    task: "Review probe",
    status,
    created_at: timestamp,
    total_tokens: 0,
    final_report: null,
    plan: {
      summary: "Probe",
      steps: [
        {
          step_number: 1,
          agent_id: agentId,
          agent_name: "Probe agent",
          model: "claude-sonnet",
          status,
          depends_on: [],
          subtask: "Probe subtask",
          attempt: 1,
          output: null as string | null,
          error:
            status === "FAILED"
              ? { code: "llm_execution_interrupted", message: "Provider outcome unknown" }
              : null,
        },
      ],
    },
  };
  run.plan.steps.push({
    ...run.plan.steps[0],
    step_number: 2,
    agent_name: "Completed agent",
    status: "COMPLETED",
    error: null,
    output: "Keep completed result",
  });
  const requests = { retry: [] as number[], created: [] as Record<string, unknown>[] };
  await page.addInitScript(() => {
    class Source extends EventTarget {
      forward = (incoming: Event) => {
        const event = (incoming as CustomEvent).detail;
        this.dispatchEvent(
          new MessageEvent(event.event, { data: JSON.stringify(event), lastEventId: event.id }),
        );
      };
      constructor(url: string) {
        super();
        window.dispatchEvent(new CustomEvent("probe-subscription", { detail: url }));
        window.addEventListener("probe-sse", this.forward);
      }
      close() {
        window.removeEventListener("probe-sse", this.forward);
      }
    }
    Object.defineProperty(window, "EventSource", { value: Source });
  });
  await page.route("**/api/v1/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    const headers = { "access-control-allow-origin": "http://localhost:3000" };
    if (route.request().method() === "OPTIONS")
      return route.fulfill({
        status: 204,
        headers: {
          ...headers,
          "access-control-allow-methods": "GET,POST,OPTIONS",
          "access-control-allow-headers": "content-type",
        },
      });
    if (path.endsWith("/retry")) {
      requests.retry.push(Number(path.split("/").at(-2)));
      run.status = "IN_PROGRESS";
      run.plan.steps[0].status = "IN_PROGRESS";
      run.plan.steps[0].error = null;
      return route.fulfill({ headers, json: run });
    }
    if (path === "/api/v1/agents" && route.request().method() === "POST") {
      const values = route.request().postDataJSON() as Record<string, unknown>;
      requests.created.push(values);
      return route.fulfill({
        headers,
        json: { ...values, id: agentId, created_at: timestamp, updated_at: timestamp },
      });
    }
    if (path.endsWith("/agents/models"))
      return route.fulfill({
        headers,
        json: {
          items: [
            {
              key: "claude-sonnet",
              tier: "balanced",
              provider: "anthropic",
              context_window: 200000,
              max_output_tokens: 128000,
            },
          ],
        },
      });
    if (path.endsWith("/settings/config"))
      return route.fulfill({
        headers,
        json: { default_model: "claude-sonnet", temperature: 0.7, max_tokens: 4096 },
      });
    if (path === "/api/v1/runs")
      return route.fulfill({ headers, json: { items: [run], total: 1 } });
    if (path === `/api/v1/runs/${id}`) return route.fulfill({ headers, json: run });
    return route.fulfill({ headers, json: { items: [], total: 0 } });
  });
  return requests;
}

for (const theme of ["dark", "light"]) {
  test.describe(theme, () => {
    test.beforeEach(async ({ page }) => {
      await page.addInitScript((value) => localStorage.setItem("theme", value), theme);
    });

    test("failed step can be retried after reload without repeating completed steps", async ({
      page,
    }) => {
      const requests = await setup(page, "FAILED");
      await page.goto(`/runs/${id}`);
      await expect(page.getByText("Provider outcome unknown")).toBeVisible();
      await expect(page.getByRole("button", { name: "Retry step" })).toHaveCount(1);
      await page.reload();
      await page.getByRole("button", { name: "Retry step" }).click();
      await expect(page.getByRole("button", { name: "Retry step" })).toHaveCount(0);
      await expect(page.getByText("Keep completed result")).toBeVisible();
      expect(requests.retry).toEqual([1]);
    });

    test("long stream preserves activity history and resumes from the latest chunk cursor", async ({
      page,
    }) => {
      await setup(page, "IN_PROGRESS");
      await page.goto(`/runs/${id}`);
      await expect(page.getByText("Probe subtask")).toHaveCount(0);
      await expect(page.getByText("Review probe", { exact: true })).toBeVisible();
      await page.evaluate(() =>
        window.dispatchEvent(
          new CustomEvent("probe-sse", {
            detail: { event: "task:started", id: "1", ts: "2026-10-14T10:00:00Z", data: {} },
          }),
        ),
      );
      await expect(page.getByText(/task:started/)).toBeVisible();
      await page.evaluate(() => {
        for (let i = 0; i < 151; i++)
          window.dispatchEvent(
            new CustomEvent("probe-sse", {
              detail: {
                event: "agent:stream_chunk",
                id: String(i + 2),
                ts: "2026-10-14T10:00:00Z",
                data: { stepNumber: 1, attempt: 1, output: "chunk" + i },
              },
            }),
          );
      });
      await expect(page.getByLabel("Output for step 1")).toHaveText("chunk150");
      await expect(page.getByText(/task:started/)).toBeVisible();
      await page.getByRole("link", { name: "Runs", exact: true }).click();
      await expect(page.getByRole("heading", { name: "Runs", exact: true })).toBeVisible();
      await page.evaluate(() => {
        window.addEventListener("probe-subscription", (event) => {
          document.documentElement.dataset.probeSubscription = (
            event as CustomEvent<string>
          ).detail;
        });
      });
      await page.getByRole("link", { name: /Probe workflow/ }).click();
      await expect(page.getByText(/task:started/)).toBeVisible();
      await expect(page.locator("html")).toHaveAttribute("data-probe-subscription", /\?after=152$/);
    });

    for (const tokens of [128000, 128001]) {
      test(`token error ${tokens} is visible after revealing advanced settings and can be corrected`, async ({
        page,
      }) => {
        const requests = await setup(page, "IN_PROGRESS");
        await page.goto("/agents");
        await page.getByRole("button", { name: "Create Agent", exact: true }).click();
        const dialog = page.getByRole("dialog");
        await dialog.getByPlaceholder("e.g., Senior Code Reviewer").fill("Probe");
        await dialog
          .getByPlaceholder("e.g., Reviews code for bugs, security, and performance")
          .fill("Probe role");
        await dialog.getByLabel("System prompt Markdown source").fill("Probe prompt");
        await dialog.getByRole("button", { name: "Advanced Settings" }).click();
        await dialog
          .getByRole("spinbutton", { name: "Max tokens", exact: true })
          .fill(String(tokens));
        await dialog.getByRole("button", { name: "Advanced Settings" }).click();
        await expect(
          dialog.getByRole("button", { name: "Create Agent", exact: true }),
        ).toBeEnabled();
        await dialog.getByRole("button", { name: "Create Agent", exact: true }).click();
        await expect(dialog).toBeVisible();
        await expect(dialog.getByRole("button", { name: "Advanced Settings" })).toHaveAttribute(
          "aria-expanded",
          "true",
        );
        await expect(dialog.getByRole("alert")).toHaveText(
          "Output tokens must leave room for input in the context window.",
        );
        await expect(
          dialog.getByRole("spinbutton", { name: "Max tokens", exact: true }),
        ).toHaveAttribute("aria-invalid", "true");
        expect(requests.created).toHaveLength(0);
        await dialog.getByRole("spinbutton", { name: "Max tokens", exact: true }).fill("4096");
        await dialog.getByRole("button", { name: "Create Agent", exact: true }).click();
        await expect(dialog).toHaveCount(0);
        expect(requests.created).toHaveLength(1);
        expect(requests.created[0].max_tokens).toBe(4096);
      });
    }
  });
}
