import { expect, test, type Page } from "@playwright/test";

const firstId = "00000000-0000-4000-8000-000000000020";
const secondId = "00000000-0000-4000-8000-000000000021";
const agentId = "00000000-0000-4000-8000-000000000001";
const timestamp = "2026-10-09T12:00:00Z";

function makeRun(id = firstId, status = "IN_PROGRESS") {
  return {
    id,
    workflow_id: agentId,
    workflow_title: id === firstId ? "Live workflow" : "Previous workflow",
    task: id === firstId ? "Actual task from API" : "Previous task",
    status,
    created_at: timestamp,
    total_tokens: 42,
    total_time_ms: 1250,
    planning_prompt_tokens: 10,
    planning_completion_tokens: 2,
    planning_time_ms: 250,
    token_budget: 1000,
    final_report: status === "COMPLETED" ? "Persisted previous report" : (null as string | null),
    plan: {
      summary: "Persisted plan",
      steps: [
        {
          step_number: 1,
          agent_id: agentId,
          agent_name: "Actual reviewer",
          model: "snapshot-model",
          status,
          depends_on: [],
          subtask: "Actual subtask",
          input: "Actual persisted input",
          output: status === "COMPLETED" ? "Previous output" : "Partial",
          attempt: 1,
          prompt_tokens: 20,
          completion_tokens: 10,
          duration_ms: 1000,
        },
        {
          step_number: 2,
          agent_id: agentId,
          agent_name: "Actual writer",
          model: "writer-model",
          status: status === "COMPLETED" ? "COMPLETED" : "PENDING",
          depends_on: [1],
          subtask: "Write summary",
          input: "Writer input",
          output: "Writer output",
          attempt: 0,
          prompt_tokens: 0,
          completion_tokens: 0,
          duration_ms: 0,
        },
      ],
    },
  };
}

async function installSSE(page: Page) {
  await page.addInitScript(() => {
    const closed: string[] = [];

    Object.defineProperty(window, "closedDashboardStreams", { value: closed });

    class MockEventSource extends EventTarget {
      onerror = null;

      constructor(public url: string) {
        super();
        window.addEventListener("dashboard-sse", this.forward);
      }

      forward = (incoming: Event) => {
        const event = (incoming as CustomEvent).detail;

        if (!this.url.includes(`/runs/${event.runId}/`)) return;

        this.dispatchEvent(
          new MessageEvent(event.event, {
            data: JSON.stringify(event),
            lastEventId: event.id ?? "",
          }),
        );
      };

      close() {
        closed.push(this.url);
        window.removeEventListener("dashboard-sse", this.forward);
      }
    }

    Object.defineProperty(window, "EventSource", { value: MockEventSource });
  });
}

async function emit(
  page: Page,
  event: string,
  data: Record<string, unknown>,
  id: string,
  runId = firstId,
) {
  await page.evaluate(
    (detail) => window.dispatchEvent(new CustomEvent("dashboard-sse", { detail })),
    { event, data, id, runId, ts: timestamp },
  );
}

for (const theme of ["dark", "light"]) {
  test(`Dashboard cold start fits the viewport in ${theme}`, async ({ page }) => {
    await page.addInitScript((value) => localStorage.setItem("theme", value), theme);

    await page.route("**/api/v1/**", (route) =>
      route.fulfill({
        headers: { "access-control-allow-origin": "*" },
        json: { items: [], total: 0 },
      }),
    );

    await page.setViewportSize({ width: 1632, height: 1290 });
    await page.goto("/");

    await expect(
      page.getByText("No runs yet. Start a workflow to monitor its execution."),
    ).toBeVisible();

    await expect(page.getByText("No events yet.")).toBeVisible();

    for (const width of [1632, 1440, 1280]) {
      await page.setViewportSize({ width, height: 1290 });

      await expect(async () => {
        const dimensions = await page.evaluate(() => ({
          height: document.documentElement.scrollHeight,
          width: document.documentElement.scrollWidth,
          viewportHeight: window.innerHeight,
          viewportWidth: window.innerWidth,
        }));

        expect(dimensions.height).toBe(dimensions.viewportHeight);
        expect(dimensions.width).toBe(dimensions.viewportWidth);
      }).toPass();
    }

    // Small windows must retain natural scrolling so every panel stays reachable.
    await page.setViewportSize({ width: 1024, height: 720 });

    expect(await page.evaluate(() => document.documentElement.scrollHeight)).toBeGreaterThan(720);

    const inspectorFooter = page
      .getByLabel("Agent inspector")
      .getByText("Waiting for a run", {
        exact: true,
      })
      .last();

    await inspectorFooter.scrollIntoViewIfNeeded();
    await expect(inspectorFooter).toBeInViewport();
  });

  test(`Dashboard follows the latest active agent in ${theme}`, async ({ page }) => {
    await page.addInitScript((value) => localStorage.setItem("theme", value), theme);
    await installSSE(page);

    const active = makeRun();

    active.plan.steps[0].status = "PENDING";

    await page.route("**/api/v1/**", (route) => {
      const pathname = new URL(route.request().url()).pathname;
      const headers = { "access-control-allow-origin": "http://localhost:3000" };

      return route.fulfill({
        headers,
        json:
          pathname === `/api/v1/runs/${firstId}`
            ? active
            : { items: pathname === "/api/v1/runs" ? [active] : [], total: 1 },
      });
    });

    await page.goto("/");

    const inspector = page.getByLabel("Agent inspector");

    await expect(
      inspector.getByRole("heading", { name: "Actual reviewer", exact: true }),
    ).toBeVisible();

    active.plan.steps[1].status = "IN_PROGRESS";

    await emit(page, "agent:status_change", { stepNumber: 2, status: "IN_PROGRESS" }, "1");
    await expect(inspector.getByText("writer-model", { exact: true })).toBeVisible();

    active.plan.steps[0].status = "IN_PROGRESS";

    await emit(page, "agent:status_change", { stepNumber: 1, status: "IN_PROGRESS" }, "2");
    await expect(page.getByText("Active Nodes: 2")).toBeVisible();
    await expect(inspector.getByText("snapshot-model", { exact: true })).toBeVisible();
    await page.getByRole("button", { name: "Inspect step 2: Actual writer" }).click();
    await expect(inspector.getByText("snapshot-model", { exact: true })).toBeVisible();

    await emit(
      page,
      "agent:stream_chunk",
      {
        stepNumber: 2,
        attempt: 1,
        output: "Parallel writer output",
        textDelta: "output",
        reset: false,
      },
      "3",
    );

    await expect(inspector.getByText("snapshot-model", { exact: true })).toBeVisible();

    active.plan.steps[0].status = "COMPLETED";
    active.plan.steps[1].output = "Parallel writer output";

    await emit(page, "agent:completed", { stepNumber: 1 }, "4");
    await expect(inspector.getByText("writer-model", { exact: true })).toBeVisible();
    await expect(inspector.getByLabel("Output for step 2")).toHaveText("Parallel writer output");
    await page.reload();
    await expect(inspector.getByText("writer-model", { exact: true })).toBeVisible();

    active.plan.steps[0].status = "IN_PROGRESS";
    active.plan.steps[0].attempt = 2;

    await emit(page, "agent:status_change", { stepNumber: 1, status: "IN_PROGRESS" }, "5");
    await expect(inspector.getByText("snapshot-model", { exact: true })).toBeVisible();
    await expect(inspector.getByText("Actual persisted input", { exact: true })).toBeVisible();
  });

  test(`Dashboard uses persisted runs and live events in ${theme}`, async ({ page }) => {
    await page.addInitScript((value) => localStorage.setItem("theme", value), theme);
    await installSSE(page);

    const active = makeRun(),
      previous = makeRun(secondId, "COMPLETED");

    await page.route("**/api/v1/**", async (route) => {
      const pathname = new URL(route.request().url()).pathname;
      const headers = { "access-control-allow-origin": "http://localhost:3000" };

      if (pathname === "/api/v1/runs")
        return route.fulfill({ headers, json: { items: [previous, active], total: 2 } });

      if (pathname === `/api/v1/runs/${firstId}`) return route.fulfill({ headers, json: active });

      if (pathname === `/api/v1/runs/${secondId}`)
        return route.fulfill({ headers, json: previous });

      return route.fulfill({ headers, json: { items: [], total: 0 } });
    });

    await page.goto("/");

    const inspector = page.getByLabel("Agent inspector");

    await expect(page.getByText("Active Nodes: 1")).toBeVisible();
    await expect(page.getByRole("combobox", { name: "Monitored run" })).toHaveCount(0);
    await expect(inspector.getByRole("heading", { name: "Output", exact: true })).toHaveCount(0);

    await expect(inspector.getByRole("heading", { name: "Run totals", exact: true })).toHaveCount(
      0,
    );

    await page.getByRole("button", { name: "More pipeline options" }).click();

    await expect(page.getByRole("combobox", { name: "Monitored run" })).toContainText(
      "Live workflow",
    );

    await expect(page.getByText("Active Nodes: 1")).toBeVisible();
    await expect(page.getByLabel("Monitored task")).toHaveText("Actual task from API");
    await page.getByRole("button", { name: "More pipeline options" }).click();
    await expect(inspector.getByText("Actual persisted input", { exact: true })).toBeVisible();
    await expect(inspector.getByText("snapshot-model", { exact: true })).toBeVisible();
    await expect(inspector.getByLabel("Step tokens")).toBeVisible();
    await expect(inspector.getByText("● Prompt (20)")).toBeVisible();
    await expect(inspector.getByText("● Completion (10)")).toBeVisible();

    const pipeline = page.getByRole("region", { name: "Execution pipeline" });

    await expect(pipeline.locator("svg.lucide-arrow-right")).toHaveCount(1);

    await expect(inspector.getByRole("progressbar", { name: "Completed steps" })).toHaveAttribute(
      "aria-valuenow",
      "0",
    );

    const tokenBar = inspector.getByLabel("Step token distribution");

    await expect(tokenBar.locator("span").first()).toHaveAttribute("style", /66\.66/);
    await expect(tokenBar.locator("span").last()).toHaveAttribute("style", /33\.33/);
    await expect(page.getByText(/Repo Analyzer|QA Tester|sample data|12,402/)).toHaveCount(0);

    const chunk = {
      agentId,
      stepNumber: 1,
      attempt: 1,
      reset: false,
      textDelta: " result",
      output: "Partial result",
    };

    active.plan.steps[0].output = "Partial result";

    await emit(page, "agent:status_change", { stepNumber: 1, status: "IN_PROGRESS" }, "9");

    active.plan.steps[0].output = "";

    await emit(
      page,
      "agent:stream_chunk",
      { ...chunk, reset: true, textDelta: "", output: "" },
      "10",
    );

    await expect(inspector.getByText("Waiting for model response…", { exact: true })).toBeVisible();

    await expect(
      page
        .getByLabel("Run orchestration events")
        .getByText("Actual reviewer: waiting for the model response.", { exact: true }),
    ).toBeVisible();

    active.plan.steps[0].output = "Partial result";

    await emit(page, "agent:stream_chunk", chunk, "11");
    await expect(inspector.getByLabel("Output for step 1")).toHaveText("Partial result");
    await expect(inspector.getByText("Receiving model response…", { exact: true })).toBeVisible();
    await emit(page, "agent:stream_chunk", chunk, "11");

    await expect(
      page.getByLabel("Run orchestration events").getByLabel("agent:stream_chunk", { exact: true }),
    ).toHaveCount(1);

    await expect(
      page
        .getByLabel("Run orchestration events")
        .getByText("Actual reviewer: preparing the model request.", { exact: true }),
    ).toBeVisible();

    await page.getByRole("button", { name: "Clear", exact: true }).click();
    await expect(page.getByText("Console cleared. Waiting for new events.")).toBeVisible();

    await emit(
      page,
      "agent:tool_result",
      { stepNumber: 1, toolName: "calculator", ok: true, summary: "Tool\ncompleted." },
      "12",
    );

    await expect(
      page.getByLabel("Run orchestration events").getByLabel("agent:tool_result", { exact: true }),
    ).toBeVisible();

    await expect(
      page.getByLabel("Run orchestration events").getByText("Tool: calculator", { exact: true }),
    ).toBeVisible();

    await expect(
      page.getByLabel("Run orchestration events").getByText("Tool completed.", { exact: true }),
    ).toBeVisible();

    await emit(page, "task:paused", { taskId: firstId, pauseReasons: ["MODEL_UNAVAILABLE"] }, "13");

    await expect(
      page.getByLabel("Run orchestration events").getByText(/An agent model is unavailable/),
    ).toBeVisible();

    await page.getByRole("button", { name: "Inspect step 2: Actual writer" }).click();
    await expect(inspector.getByText("Actual persisted input", { exact: true })).toBeVisible();
    await page.getByRole("button", { name: "More pipeline options" }).click();
    await page.getByRole("combobox", { name: "Monitored run" }).click();
    await page.getByRole("option", { name: /Previous workflow/ }).click();
    await expect(page).toHaveURL(new RegExp(`\\?run=${secondId}`));
    await expect(inspector.getByLabel("Output for step 1")).toHaveText("Previous output");

    await expect(inspector.getByRole("progressbar", { name: "Completed steps" })).toHaveAttribute(
      "aria-valuenow",
      "100",
    );

    await expect(
      page.getByLabel("Run orchestration events").getByLabel("agent:tool_result", { exact: true }),
    ).toHaveCount(0);

    const closed = await page.evaluate(
      () => (window as unknown as { closedDashboardStreams: string[] }).closedDashboardStreams,
    );

    expect(closed.some((url) => url.includes(firstId) && url.endsWith("?after=0"))).toBe(true);

    await emit(page, "agent:stream_chunk", { ...chunk, output: "Stale first run" }, "14");
    await expect(inspector.getByLabel("Output for step 1")).toHaveText("Previous output");
    await page.reload();
    await page.getByRole("button", { name: "More pipeline options" }).click();

    await expect(page.getByRole("combobox", { name: "Monitored run" })).toContainText(
      "Previous workflow",
    );

    await expect(inspector.getByText("Persisted previous report")).toBeVisible();
    await emit(page, "agent:stream_chunk", { ...chunk, output: "Old replay" }, "15", secondId);
    await expect(inspector.getByLabel("Output for step 1")).toHaveText("Previous output");
  });

  test(`Dashboard has empty and API error states in ${theme}`, async ({ page }) => {
    await page.addInitScript((value) => localStorage.setItem("theme", value), theme);

    await page.route("**/api/v1/**", (route) =>
      route.fulfill({
        headers: { "access-control-allow-origin": "http://localhost:3000" },
        json: { items: [], total: 0 },
      }),
    );

    await page.goto("/");

    await expect(
      page.getByText("No runs yet. Start a workflow to monitor its execution."),
    ).toBeVisible();

    await expect(page.getByText("Active Nodes: 0")).toBeVisible();
    await expect(page.getByText(/QA Tester|Repo Analyzer|sample data/)).toHaveCount(0);

    await page.route(/\/api\/v1\/runs(?:\?.*)?$/, (route) =>
      route.fulfill({
        status: 503,
        headers: { "access-control-allow-origin": "http://localhost:3000" },
        json: { error: { message: "Unavailable" } },
      }),
    );

    await page.reload();

    await expect(page.getByRole("alert").filter({ hasText: "Could not load runs." })).toBeVisible({
      timeout: 15000,
    });
  });
}
