import { expect, test, type Page } from "@playwright/test";
import type { DecisionResolution, RunDetails } from "../src/features/runs/types";

const runId = "00000000-0000-4000-8000-000000000031";
const agentId = "00000000-0000-4000-8000-000000000032";
const decisionId = "00000000-0000-4000-8000-000000000033";
const timestamp = "2026-10-21T10:00:00Z";

async function setup(page: Page, theme: string, status: "PAUSED" | "IN_PROGRESS" = "PAUSED") {
  const run: RunDetails = {
    id: runId,
    workflow_id: agentId,
    workflow_title: "Review workflow",
    task: "Review checkout",
    status,
    created_at: timestamp,
    total_tokens: 28,
    pause_reasons: ["USER_DECISION_REQUIRED"],
    plan: {
      steps: [
        {
          step_number: 1,
          agent_id: agentId,
          agent_name: "QA reviewer",
          status: "COMPLETED",
          depends_on: [],
          output: "Original QA result",
        },
        {
          step_number: 2,
          agent_id: agentId,
          agent_name: "Publisher",
          status: "PENDING",
          depends_on: [1],
        },
      ],
    },
    decisions: [
      {
        id: decisionId,
        source_step_number: 1,
        status: "PENDING",
        issues: [
          {
            title: "Empty email accepted",
            description: "Submit an empty email; validation should reject it.",
            severity: "high",
          },
        ],
        suggested_agent_id: agentId,
        suggested_task: "Fix empty email validation.",
        resolution: null,
        created_at: timestamp,
        resolved_at: null,
        followup_step_numbers: [],
      },
    ],
  };
  const requests: DecisionResolution[] = [];
  const state = { fail: false };
  await page.addInitScript((theme) => {
    localStorage.setItem("theme", theme);
    class Source extends EventTarget {
      constructor() {
        super();
        window.addEventListener("decision-test-event", (event) => {
          const detail = (event as CustomEvent).detail;
          this.dispatchEvent(
            new MessageEvent(detail.event, {
              data: JSON.stringify(detail),
              lastEventId: detail.id,
            }),
          );
        });
      }
      close() {}
    }
    Object.defineProperty(window, "EventSource", { value: Source });
  }, theme);
  await page.route("**/api/v1/**", async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname.replace("/api/v1", "");
    const headers = {
      "access-control-allow-origin": "http://localhost:3000",
      "access-control-allow-methods": "GET,POST,OPTIONS",
      "access-control-allow-headers": "content-type",
    };
    if (request.method() === "OPTIONS") return route.fulfill({ status: 204, headers });
    if (path === `/runs/${runId}/decisions/${decisionId}/resolve`) {
      const payload = request.postDataJSON() as DecisionResolution;
      requests.push(payload);
      if (state.fail)
        return route.fulfill({
          status: 409,
          headers,
          json: { error: { code: "invalid_run_state", message: "Selected agent is unavailable." } },
        });
      run.status = payload.action === "cancel" ? "CANCELLED" : "IN_PROGRESS";
      run.pause_reasons = [];
      const decision = run.decisions![0];
      decision.status = "RESOLVED";
      decision.resolution = payload;
      decision.resolved_at = timestamp;
      if (payload.action === "assign_fixes" && run.plan && !Array.isArray(run.plan)) {
        decision.followup_step_numbers = [3, 4];
        run.plan.steps.push(
          {
            step_number: 3,
            agent_id: agentId,
            agent_name: "Developer",
            status: "PENDING",
            depends_on: [1],
            subtask: payload.task,
          },
          {
            step_number: 4,
            agent_id: agentId,
            agent_name: "QA reviewer",
            status: "PENDING",
            depends_on: [3],
          },
        );
      }
      return route.fulfill({ headers, json: run });
    }
    if (path === `/runs/${runId}`) return route.fulfill({ headers, json: run });
    if (path === "/runs") return route.fulfill({ headers, json: { items: [run], total: 1 } });
    if (path === "/agents")
      return route.fulfill({
        headers,
        json: {
          items: [{ id: agentId, name: "Developer", role: "Fix code", available: true }],
          total: 1,
        },
      });
    return route.fulfill({ headers, json: { items: [], total: 0 } });
  });
  return { run, requests, state };
}

for (const theme of ["light", "dark"]) {
  for (const surface of ["dashboard", "details"]) {
    test(`Assign fixes persists and updates ${surface} in ${theme}`, async ({ page }) => {
      const { requests } = await setup(page, theme);
      await page.goto(surface === "dashboard" ? `/?run=${runId}` : `/runs/${runId}`);
      const dialog = page.getByRole("dialog", { name: "Your decision is required" });
      const card = dialog.getByRole("region", { name: "Decision for step 1" });
      await expect(dialog).toBeVisible();
      await expect(card.getByText("Empty email accepted", { exact: true })).toBeVisible();
      await page.keyboard.press("Escape");
      await expect(dialog).toBeHidden();
      expect(requests).toEqual([]);
      await page.getByRole("button", { name: "Review decisions (1)", exact: true }).click();
      await expect(dialog).toBeVisible();
      await page.reload();
      await expect(card.getByRole("button", { name: "Assign fixes", exact: true })).toBeEnabled();
      await card
        .getByLabel("Fix task", { exact: true })
        .fill("Fix email and whitespace validation");
      await card.getByLabel("Comment (optional)").fill("Keep previous QA evidence");
      await card.getByRole("button", { name: "Assign fixes", exact: true }).click();
      await expect(dialog).toHaveCount(0);
      await expect(card).toHaveCount(0);
      expect(requests).toEqual([
        {
          action: "assign_fixes",
          agent_id: agentId,
          task: "Fix email and whitespace validation",
          comment: "Keep previous QA evidence",
        },
      ]);
      await page.getByText("Decision history (1)", { exact: true }).click();
      await expect(page.getByText("Fixes assigned; new steps 3, 4", { exact: true })).toBeVisible();
      await page.reload();
      await expect(page.getByText("Decision history (1)", { exact: true })).toBeVisible();
      await expect(card).toHaveCount(0);
    });
  }
  test(`Continue, error recovery and cancellation in ${theme}`, async ({ page }) => {
    const { requests, state } = await setup(page, theme);
    await page.goto(`/runs/${runId}`);
    const card = page.getByRole("region", { name: "Decision for step 1" });
    state.fail = true;
    await card.getByRole("button", { name: "Continue without fixes" }).click();
    await expect(
      card.getByRole("alert").filter({ hasText: "Selected agent is unavailable." }),
    ).toBeVisible();
    await expect(card.getByRole("button", { name: "Continue without fixes" })).toBeEnabled();
    state.fail = false;
    await card.getByRole("button", { name: "Continue without fixes" }).click();
    await expect(card).toHaveCount(0);
    expect(requests.at(-1)?.action).toBe("continue");
  });
  test(`Active branches drain and decisions arrive through SSE in ${theme}`, async ({ page }) => {
    const { run, requests } = await setup(page, theme, "IN_PROGRESS");
    const decision = run.decisions![0];
    run.decisions = [];
    await page.goto(`/?run=${runId}`);
    const card = page.getByRole("region", { name: "Decision for step 1" });
    await expect(card).toHaveCount(0);
    run.decisions = [decision];
    await page.evaluate(
      (detail) => window.dispatchEvent(new CustomEvent("decision-test-event", { detail })),
      {
        event: "decision:required",
        data: { taskId: runId, decision },
        runId,
        ts: timestamp,
        id: "1",
      },
    );
    await expect(page.getByRole("dialog", { name: "Your decision is required" })).toBeVisible();
    await expect(card.getByText(/Active steps are finishing/)).toBeVisible();
    await expect(card.getByRole("button", { name: "Assign fixes", exact: true })).toBeDisabled();
    await expect(card.getByRole("button", { name: "Continue without fixes" })).toBeDisabled();
    await card.getByRole("button", { name: "Cancel run", exact: true }).click();
    await expect(card).toHaveCount(0);
    expect(requests.at(-1)?.action).toBe("cancel");
  });
}
