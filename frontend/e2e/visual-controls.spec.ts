import { expect, test, type Page } from "@playwright/test";

const timestamp = "2026-10-20T10:00:00Z";
const agent = {
  id: "00000000-0000-4000-8000-000000000001",
  name: "Reviewer",
  role: "Review",
  system_prompt: "Review the task",
  model: "claude-sonnet",
  temperature: 0.7,
  max_tokens: 4096,
  context_window: 128000,
  tools: [],
  created_at: timestamp,
  updated_at: timestamp,
};
const title = "Release preparation with implementation, quality assurance and final documentation";

async function setup(page: Page, theme: string) {
  await page.addInitScript((value) => localStorage.setItem("theme", value), theme);
  await page.route("**/api/v1/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    const headers = { "access-control-allow-origin": "http://localhost:3000" };
    if (route.request().method() === "OPTIONS")
      return route.fulfill({
        status: 204,
        headers: {
          ...headers,
          "access-control-allow-methods": "GET,OPTIONS",
          "access-control-allow-headers": "content-type",
        },
      });
    let json: unknown = { items: [], total: 0 };
    if (path.endsWith("/agents")) json = { items: [agent], total: 1 };
    if (path.endsWith("/agents/models"))
      json = {
        items: [
          {
            key: "claude-sonnet",
            provider: "anthropic",
            tier: "balanced",
            context_window: 200000,
            enabled: true,
          },
        ],
      };
    if (path.endsWith("/settings/config"))
      json = {
        default_model: "claude-sonnet",
        temperature: 0.7,
        max_tokens: 4096,
        llm_provider_mode: "mock",
        code_executor_backend: "disabled",
      };
    if (path.endsWith("/workflows"))
      json = {
        items: [
          {
            id: agent.id,
            title,
            execution_type: "sequential",
            steps: [
              { step_number: 1, agent_id: agent.id, depends_on: [], input_transform: "" },
              { step_number: 2, agent_id: agent.id, depends_on: [1], input_transform: "" },
            ],
            graph_layout: { "1": { x: 80, y: 80 }, "2": { x: 340, y: 230 } },
            created_at: timestamp,
            updated_at: timestamp,
          },
        ],
        total: 1,
      };
    await route.fulfill({ headers, json });
  });
}

async function checkPopup(page: Page) {
  const popup = page.locator('[data-slot="select-content"][data-open]');
  await expect(popup).toBeVisible();
  await popup.evaluate(async (el) => {
    await Promise.allSettled(el.getAnimations().map((animation) => animation.finished));
  });
  const icon = page.locator(
    '[data-slot="select-trigger"][aria-expanded="true"] [data-slot="select-icon"]',
  );
  await expect.poll(() => icon.evaluate((el) => getComputedStyle(el).rotate)).toBe("180deg");
  expect(await popup.evaluate((el) => el.scrollWidth <= el.clientWidth + 1)).toBe(true);
  const box = await popup.boundingBox();
  expect(box!.x).toBeGreaterThanOrEqual(0);
  expect(box!.x + box!.width).toBeLessThanOrEqual(page.viewportSize()!.width);
}

for (const theme of ["light", "dark"]) {
  test(`${theme}: workflow popup fits content and viewport`, async ({ page }, info) => {
    await setup(page, theme);
    await page.goto("/");
    const trigger = page.getByRole("combobox", { name: "Workflow", exact: true });
    const icon = trigger.locator('[data-slot="select-icon"]');
    await expect.poll(() => icon.evaluate((el) => getComputedStyle(el).rotate)).toBe("none");
    await trigger.click();
    await expect(page.getByRole("option", { name: title })).toBeVisible();
    await checkPopup(page);
    await page.screenshot({ path: info.outputPath("workflow-select.png"), animations: "disabled" });
    expect(
      (await page.locator('[data-slot="select-content"][data-open]').boundingBox())!.width,
    ).toBeGreaterThan((await trigger.boundingBox())!.width);
    await page.getByRole("option", { name: title }).click();
    await expect.poll(() => icon.evaluate((el) => getComputedStyle(el).rotate)).toBe("none");
    await page.setViewportSize({ width: 540, height: 900 });
    await trigger.click();
    await checkPopup(page);
    await page.screenshot({ path: info.outputPath("workflow-select-narrow.png") });
  });

  test(`${theme}: agent close button and context trigger`, async ({ page }, info) => {
    await setup(page, theme);
    await page.goto("/agents");
    await page.locator("article").getByRole("button").first().click();
    const close = page.getByRole("button", { name: "Close details" });
    await page.screenshot({ path: info.outputPath("agent-details.png"), animations: "disabled" });
    const box = await close.boundingBox();
    expect(Math.abs(box!.width - box!.height)).toBeLessThan(0.1);
    expect(await close.evaluate((el) => getComputedStyle(el).backgroundColor)).toBe(
      "rgba(0, 0, 0, 0)",
    );
    await close.click();
    await page.getByRole("button", { name: "Edit Reviewer", exact: true }).click();
    await page.getByRole("button", { name: "Advanced Settings" }).click();
    const context = page.getByRole("combobox", { name: "Context window", exact: true });
    await page.screenshot({ path: info.outputPath("agent-dialog.png") });
    expect(await context.evaluate((el) => getComputedStyle(el).display)).toBe("flex");
    const aligned = await context.evaluate((el) => {
      const r = el.getBoundingClientRect();
      const icon = el.querySelector("svg")!.getBoundingClientRect();
      return (
        Math.abs(icon.y + icon.height / 2 - r.y - r.height / 2) < 1 && icon.x > r.x + r.width / 2
      );
    });
    expect(aligned).toBe(true);
    await context.click();
    await checkPopup(page);
    await page.getByRole("option", { name: "32K tokens", exact: true }).click();
    await expect(context).toContainText("32K tokens");
    await page.getByRole("combobox", { name: "AI model", exact: true }).click();
    await checkPopup(page);
  });

  test(`${theme}: shared selects keep their layout on agents and settings`, async ({
    page,
  }, info) => {
    await setup(page, theme);
    await page.goto("/agents");
    await page.getByRole("combobox", { name: "Filter by model" }).click();
    await checkPopup(page);
    await page.screenshot({ path: info.outputPath("agent-filter.png") });
    await page.getByRole("option", { name: "All models", exact: true }).click();
    await page.goto("/settings");
    for (const name of ["Theme", "Default model"]) {
      const trigger = page.getByRole("combobox", { name, exact: true });
      await trigger.click();
      await checkPopup(page);
      const popupBox = await page.locator('[data-slot="select-content"][data-open]').boundingBox();
      const triggerBox = await trigger.boundingBox();
      expect(popupBox!.width).toBeGreaterThanOrEqual(triggerBox!.width - 1);
      await page.screenshot({ path: info.outputPath(`settings-${name.replaceAll(" ", "-")}.png`) });
      await trigger.press("Escape");
    }
  });

  test(`${theme}: graph endpoints meet handles after opening and zoom`, async ({ page }, info) => {
    await setup(page, theme);
    await page.goto("/workflows");
    await page.getByRole("button", { name: `Edit ${title}`, exact: true }).click();
    const path = page.locator(".react-flow__edge-path");
    await expect(path).toBeVisible();
    // Measure after the dialog's opening animation has completed.
    await page.locator('[data-slot="dialog-content"]').evaluate(async (el) => {
      await Promise.allSettled(el.getAnimations().map((animation) => animation.finished));
    });
    const errors = () =>
      path.evaluate((el) => {
        const edge = el as SVGPathElement;
        const matrix = edge.getScreenCTM()!;
        return [
          [
            edge.getPointAtLength(0),
            document.querySelector('.react-flow__node[data-id="1"] .source')!,
          ],
          [
            edge.getPointAtLength(edge.getTotalLength()),
            document.querySelector('.react-flow__node[data-id="2"] .target')!,
          ],
        ].map(([point, handle], index) => {
          const p = (point as DOMPoint).matrixTransform(matrix);
          const r = (handle as Element).getBoundingClientRect();
          return Math.hypot(p.x - r.x - r.width / 2, p.y - (index === 0 ? r.bottom : r.top));
        });
      });
    await page.screenshot({ path: info.outputPath("workflow-graph.png") });
    expect(Math.max(...(await errors()))).toBeLessThan(1);
    await page.getByRole("button", { name: "Zoom In", exact: true }).click();
    await expect.poll(async () => Math.max(...(await errors()))).toBeLessThan(1);
    await page.getByRole("combobox", { name: "Arrange preset" }).click();
    await checkPopup(page);
  });
}
