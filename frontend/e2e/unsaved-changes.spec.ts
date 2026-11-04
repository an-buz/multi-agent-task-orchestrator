import { expect, test } from "@playwright/test";

const agentId = "00000000-0000-4000-8000-000000000001";
const timestamp = "2026-11-04T10:00:00Z";
const agent = {
  id: agentId,
  name: "Reviewer",
  role: "Review",
  system_prompt: "Review",
  model: "claude-sonnet",
  temperature: 0.7,
  max_tokens: 4096,
  context_window: 128000,
  tools: [],
  created_at: timestamp,
  updated_at: timestamp,
};

for (const theme of ["light", "dark"]) {
  test.beforeEach(async ({ page }) => {
    await page.addInitScript((value) => localStorage.setItem("theme", value), theme);
    await page.route("**/api/v1/**", async (route) => {
      const path = new URL(route.request().url()).pathname;
      const headers = { "access-control-allow-origin": "http://localhost:3000" };
      let json: unknown = { items: [], total: 0 };

      if (path.endsWith("/agents")) json = { items: [agent], total: 1 };
      if (path.endsWith("/agents/models"))
        json = {
          items: [
            {
              key: "claude-sonnet",
              provider: "anthropic",
              tier: "balanced",
              context_window: 128000,
              max_output_tokens: 8192,
            },
          ],
        };
      if (path.endsWith("/config"))
        json = { default_model: "claude-sonnet", temperature: 0.7, max_tokens: 4096 };

      await route.fulfill({ headers, json });
    });
  });

  test(`Esc on a selected dirty graph preserves nodes in ${theme}`, async ({ page }) => {
    await page.goto("/workflows");
    await page.getByRole("button", { name: "New workflow" }).click();
    await page.getByPlaceholder("Workflow title").fill("Unsaved graph");
    await page.getByRole("button", { name: "Reviewer claude-sonnet" }).click();
    await page.locator(".react-flow__node").click();
    await page.locator(".react-flow__node").focus();
    await page.keyboard.press("Escape");

    const confirmation = page.getByRole("alertdialog", { name: "Discard workflow changes?" });

    await expect(confirmation).toBeVisible();
    await page.keyboard.press("Escape");
    await expect(confirmation).toBeHidden();
    await expect(page.locator(".react-flow__node")).toHaveCount(1);
    await expect(page.getByPlaceholder("Workflow title")).toHaveValue("Unsaved graph");
    await page.mouse.click(2, 2);
    await expect(confirmation).toBeVisible();
    await confirmation.getByRole("button", { name: "Keep editing" }).click();
    await expect(page.locator(".react-flow__node")).toHaveCount(1);
    await page.getByRole("button", { name: "Close editor" }).click();
    await confirmation.getByRole("button", { name: "Discard changes" }).click();
    await expect(page.getByRole("dialog", { name: "Workflow editor" })).toBeHidden();
    await page.getByRole("button", { name: "New workflow" }).click();
    await expect(page.locator(".react-flow__node")).toHaveCount(0);
    await page.keyboard.press("Escape");
    await expect(confirmation).toBeHidden();
    await expect(page.getByRole("dialog", { name: "Workflow editor" })).toBeHidden();
  });

  test(`agent prompt survives Esc and outside dismissal in ${theme}`, async ({ page }) => {
    await page.goto("/agents");
    await page.getByRole("button", { name: "Edit Reviewer" }).click();

    const prompt = page.getByRole("textbox", { name: "System prompt Markdown source" });
    const text = "Long system prompt. ".repeat(100);

    await prompt.fill(text);
    await page.keyboard.press("Escape");

    const confirmation = page.getByRole("alertdialog", { name: "Discard agent changes?" });

    await expect(confirmation).toBeVisible();
    await confirmation.getByRole("button", { name: "Keep editing" }).click();
    await expect(prompt).toHaveValue(text);
    await page.mouse.click(2, 2);
    await expect(confirmation).toBeVisible();
    await page.keyboard.press("Escape");
    await expect(prompt).toHaveValue(text);
    await page.getByRole("button", { name: "Close dialog" }).click();
    await confirmation.getByRole("button", { name: "Discard changes" }).click();
    await expect(page.getByRole("dialog", { name: "Edit Agent", exact: true })).toBeHidden();
  });
}
