import { readFile } from "node:fs/promises";
import { expect, test } from "@playwright/test";
import type { RunDetails, RunPlan } from "../src/features/runs/types";

const apiURL = process.env.E2E_LIVE_API_URL!;

for (const theme of ["dark", "light"]) {
  test(`UI workflow executes through real worker and SSE in ${theme}`, async ({
    page,
    request,
  }) => {
    const errors: string[] = [];
    page.on("pageerror", (error) => errors.push(error.message));
    await page.addInitScript((value) => localStorage.setItem("theme", value), theme);
    const prefix = `Live ${theme}`;
    const names = [`${prefix} Analyst`, `${prefix} Reviewer`];
    await page.goto("/");
    await expect(page.locator("html")).toHaveClass(new RegExp(theme));

    for (const name of names) {
      await page.getByRole("button", { name: "Create Agent", exact: true }).click();
      const dialog = page.getByRole("dialog");
      await dialog.getByPlaceholder("e.g., Senior Code Reviewer").fill(name);
      await dialog
        .getByPlaceholder("e.g., Reviews code for bugs, security, and performance")
        .fill(name.endsWith("Analyst") ? "Analyze requirements" : "Review the analysis");
      await dialog
        .getByLabel("System prompt Markdown source")
        .fill("Complete your assigned task concisely.");
      const saved = page.waitForResponse(
        (response) =>
          response.url() === `${apiURL}/agents` && response.request().method() === "POST",
      );
      await dialog.getByRole("button", { name: "Create Agent", exact: true }).click();
      expect((await saved).status()).toBe(201);
      await expect(dialog).toBeHidden();
    }

    await page.goto("/workflows");
    await page.getByRole("button", { name: "New workflow" }).click();
    const editor = page.getByRole("dialog");
    await editor.getByPlaceholder("Workflow title").fill(`${prefix} handoff`);
    // The model is selected by the app's configured default, not a test fixture.
    for (const name of names) await editor.getByRole("button", { name: new RegExp(name) }).click();
    await editor.getByRole("combobox", { name: "Arrange preset" }).click();
    await page.getByRole("option", { name: "Sequential chain" }).click();
    await expect(editor.locator(".react-flow__node")).toHaveCount(2);
    await expect(editor.locator(".react-flow__edge-path")).toHaveCount(1);
    const workflowSaved = page.waitForResponse(
      (response) =>
        response.url() === `${apiURL}/workflows` && response.request().method() === "POST",
    );
    await editor.getByRole("button", { name: "Save workflow" }).click();
    const workflowResponse = await workflowSaved;
    expect(workflowResponse.status()).toBe(201);
    const workflow = await workflowResponse.json();
    expect(workflow.steps.map((step: { depends_on: number[] }) => step.depends_on)).toEqual([
      [],
      [1],
    ]);
    await expect(editor).toBeHidden();

    await page.goto("/");
    await page.getByRole("combobox", { name: "Workflow", exact: true }).click();
    await page.getByRole("option", { name: `${prefix} handoff` }).click();
    await page
      .getByLabel("Workflow task definition")
      .fill("Analyze and review a task board release.");
    const created = page.waitForResponse(
      (response) => response.url() === `${apiURL}/runs` && response.request().method() === "POST",
    );
    await page.getByRole("button", { name: "Decompose and Run" }).click();
    const createdResponse = await created;
    expect(createdResponse.status()).toBe(201);
    const { id } = await createdResponse.json();
    await expect(page.getByRole("heading", { name: "Plan preview" })).toBeVisible();
    const readRun = async (): Promise<RunDetails> => {
      const response = await request.get(`${apiURL}/runs/${id}`);
      expect(response.ok()).toBe(true);
      return response.json();
    };
    const planned = await readRun();
    expect(planned.status).toBe("AWAITING_CONFIRMATION");
    expect(
      (planned.plan as RunPlan).steps.map((step) => [step.status, step.attempt, step.output]),
    ).toEqual([
      ["PENDING", 0, null],
      ["PENDING", 0, null],
    ]);
    // A second read after a real reload must still require explicit confirmation.
    await page.reload();
    await page.goto(`/runs/${id}`);
    await expect(page.getByRole("heading", { name: "Plan preview" })).toBeVisible();
    expect((await readRun()).status).toBe("AWAITING_CONFIRMATION");
    await page.getByLabel(`Task for ${names[0]}`).fill("Analyze release marker HANDOFF_OK.");
    await page.getByRole("button", { name: "Confirm and run" }).click();
    await expect(page.getByRole("heading", { name: "Final report" })).toBeVisible();
    const liveEvents = page
      .locator("section")
      .filter({ has: page.getByRole("heading", { name: "Live events", exact: true }) })
      .last();
    await expect(liveEvents).toContainText("agent:status_change");
    await expect(liveEvents).toContainText("task:finished");
    const completed = await readRun();
    expect(completed.status).toBe("COMPLETED");
    const steps = (completed.plan as RunPlan).steps;
    expect(steps.map((step) => [step.status, step.attempt])).toEqual([
      ["COMPLETED", 1],
      ["COMPLETED", 1],
    ]);
    expect(steps[0].output).toContain("Mock response:");
    expect(steps[1].input).toContain(steps[0].output);
    expect(steps[1].input).toContain("HANDOFF_OK");
    expect(completed.total_tokens).toBe(
      (completed.planning_prompt_tokens ?? 0) +
        (completed.planning_completion_tokens ?? 0) +
        steps.reduce(
          (sum, step) => sum + (step.prompt_tokens ?? 0) + (step.completion_tokens ?? 0),
          0,
        ),
    );

    await page.reload();
    await expect(page.getByRole("heading", { name: "Final report" })).toBeVisible();
    await expect(page.getByLabel("Output for step 2")).toHaveText(steps[1].output!);
    const downloadPromise = page.waitForEvent("download");
    await page.getByRole("button", { name: "Download JSON", exact: true }).click();
    const download = await downloadPromise;
    expect(download.suggestedFilename()).toBe(`run-${id}.json`);
    const downloaded = JSON.parse(await readFile((await download.path())!, "utf8")) as RunDetails;
    expect(downloaded.id).toBe(id);
    expect(downloaded.status).toBe("COMPLETED");
    expect(downloaded.final_report).toBe(completed.final_report);
    expect(downloaded.plan).toEqual(completed.plan);
    expect(errors).toEqual([]);
  });
}
