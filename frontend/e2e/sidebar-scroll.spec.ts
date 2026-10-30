import { expect, test } from "@playwright/test";

for (const theme of ["dark", "light"]) {
  test(`sidebar stays in view while scrolling a long run report in ${theme}`, async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 720 });
    await page.addInitScript((value) => localStorage.setItem("theme", value), theme);

    const runId = "00000000-0000-4000-8000-000000000020";

    await page.route("**/api/v1/**", async (route) => {
      const pathname = new URL(route.request().url()).pathname;
      const headers = { "access-control-allow-origin": "http://localhost:3000" };

      if (pathname === `/api/v1/runs/${runId}/events`) {
        return route.fulfill({ headers, contentType: "text/event-stream", body: "" });
      }

      if (pathname === `/api/v1/runs/${runId}`) {
        return route.fulfill({
          headers,
          json: {
            id: runId,
            workflow_id: runId,
            task: "Long report regression",
            status: "COMPLETED",
            created_at: "2026-10-30T12:00:00Z",
            total_tokens: 0,
            plan: [],
            final_report: Array.from(
              { length: 100 },
              (_, index) => `Report paragraph ${index}.`,
            ).join("\n\n"),
          },
        });
      }

      return route.fulfill({ headers, json: { items: [], total: 0 } });
    });

    await page.goto(`/runs/${runId}`);
    await expect(page.getByRole("heading", { name: "Final report" })).toBeVisible();

    const sidebar = page.getByRole("complementary");
    const initial = await sidebar.boundingBox();

    expect(initial).not.toBeNull();
    await page.evaluate(() => window.scrollTo(0, document.documentElement.scrollHeight));
    await expect.poll(() => page.evaluate(() => window.scrollY)).toBeGreaterThan(1000);
    await expect.poll(async () => (await sidebar.boundingBox())?.y).toBe(initial!.y);
    await expect(sidebar.getByRole("link", { name: "Dashboard", exact: true })).toBeInViewport();
    await expect(
      sidebar.getByRole("button", { name: "Create Agent", exact: true }),
    ).toBeInViewport();
  });
}
