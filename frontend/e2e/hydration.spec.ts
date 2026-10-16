import { expect, test } from "@playwright/test";

for (const theme of ["light", "dark"]) {
  test(`workflow sidebar hydrates after navigation and reload in ${theme} theme`, async ({
    page,
  }) => {
    const errors: string[] = [];
    page.on("pageerror", (error) => errors.push(error.message));
    page.on("console", (message) => {
      if (/hydration|server rendered HTML/i.test(message.text())) errors.push(message.text());
    });
    await page.addInitScript((value) => localStorage.setItem("theme", value), theme);
    await page.route("**/api/v1/**", (route) =>
      route.fulfill({
        json: { items: [], total: 0 },
        headers: { "access-control-allow-origin": "*" },
      }),
    );
    const response = await page.goto("/workflows");
    expect(await response?.text()).toContain('href="/models"');
    await expect(page.getByRole("heading", { name: "No workflows yet" })).toBeVisible();
    await expect(page.locator("html")).toHaveClass(new RegExp(theme));
    await page.getByRole("link", { name: "Models", exact: true }).click();
    await expect(page.getByRole("heading", { name: "Models", exact: true })).toBeVisible();
    await page.getByRole("link", { name: "Workflows", exact: true }).click();
    await expect(page.getByRole("heading", { name: "No workflows yet" })).toBeVisible();
    await page.reload();
    await expect(page.getByRole("heading", { name: "No workflows yet" })).toBeVisible();
    await expect(page.getByRole("link", { name: "Models", exact: true })).toBeVisible();
    expect(errors).toEqual([]);
  });
}
