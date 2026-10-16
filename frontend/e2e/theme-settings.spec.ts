import { expect, test } from "@playwright/test";

test("theme selection persists and system follows device changes without the API", async ({
  page,
}) => {
  await page.route("**/api/v1/**", (route) => route.abort());
  await page.emulateMedia({ colorScheme: "light" });
  await page.goto("/settings");
  const selector = page.getByRole("combobox", { name: "Theme", exact: true });
  const selectedValue = selector.locator('[data-slot="select-value"]');
  await expect(selectedValue).toHaveText("Dark");
  const root = page.locator("html");
  await expect(root).toHaveClass(/dark/);

  for (const label of ["Light", "Dark", "System"]) {
    await selector.click();
    await page.getByRole("option", { name: label, exact: true }).click();
    await expect(selectedValue).toHaveText(label);
    await expect(root).toHaveClass(label === "Dark" ? /dark/ : /light/);
    await page.reload();
    await expect(selectedValue).toHaveText(label);
    await expect(root).toHaveClass(label === "Dark" ? /dark/ : /light/);
  }
  await page.emulateMedia({ colorScheme: "dark" });
  await expect(root).toHaveClass(/dark/);
  await expect(selectedValue).toHaveText("System");
  await selector.click();
  await page.getByRole("option", { name: "Light", exact: true }).click();
  await page.emulateMedia({ colorScheme: "light" });
  await page.emulateMedia({ colorScheme: "dark" });
  await expect(root).toHaveClass(/light/);
});
