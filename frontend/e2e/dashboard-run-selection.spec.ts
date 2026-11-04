import { expect, test } from "@playwright/test";

const firstId = "00000000-0000-4000-8000-000000000031";
const latestId = "00000000-0000-4000-8000-000000000032";

for (const theme of ["light", "dark"]) {
  test(`dashboard keeps its selected run after completion in ${theme}`, async ({ page }) => {
    await page.addInitScript((value) => {
      localStorage.setItem("theme", value);

      class MockEventSource extends EventTarget {
        close() {}
      }

      Object.defineProperty(window, "EventSource", { value: MockEventSource });
    }, theme);

    let completed = false;
    let pollsAfterCompletion = 0;
    let latestGets = 0;
    let completedGets = 0;

    const run = (id: string) => ({
      id,
      workflow_id: firstId,
      task: `Selection regression ${id}`,
      status: completed && id === firstId ? "COMPLETED" : "IN_PROGRESS",
      created_at: "2026-11-04T12:00:00Z",
      total_tokens: 0,
      plan: [],
    });

    await page.route("**/api/v1/**", async (route) => {
      const pathname = new URL(route.request().url()).pathname;
      const headers = { "access-control-allow-origin": "http://localhost:3000" };

      if (pathname === "/api/v1/runs") {
        if (completed) pollsAfterCompletion += 1;

        return route.fulfill({
          headers,
          json: {
            items: completed ? [run(latestId), run(firstId)] : [run(firstId)],
            total: completed ? 2 : 1,
          },
        });
      }

      if (pathname === `/api/v1/runs/${firstId}`) {
        if (completed) completedGets += 1;

        return route.fulfill({ headers, json: run(firstId) });
      }

      if (pathname === `/api/v1/runs/${latestId}`) {
        latestGets += 1;

        return route.fulfill({ headers, json: run(latestId) });
      }

      return route.fulfill({ headers, json: { items: [], total: 0 } });
    });

    await page.goto("/?tab=output");
    await expect(page.locator("html")).toHaveClass(new RegExp(theme));
    await expect(page).toHaveURL(`/?tab=output&run=${firstId}`);
    await expect(page.locator("header").getByText(firstId, { exact: true })).toBeVisible();

    const follow = page.getByRole("button", { name: "Follow latest run" });

    await expect(follow).toBeDisabled();
    completed = true;

    await expect.poll(() => completedGets, { timeout: 15000 }).toBeGreaterThan(0);
    await expect.poll(() => pollsAfterCompletion, { timeout: 15000 }).toBeGreaterThanOrEqual(2);
    await expect(page).toHaveURL(`/?tab=output&run=${firstId}`);
    await expect(page.locator("header").getByText(firstId, { exact: true })).toBeVisible();
    expect(latestGets).toBe(0);
    await expect(follow).toBeEnabled();

    await follow.click();
    await expect(page).toHaveURL(`/?tab=output&run=${latestId}`);
    await expect(page.locator("header").getByText(latestId, { exact: true })).toBeVisible();
    await expect.poll(() => latestGets).toBeGreaterThan(0);
    await expect(follow).toBeDisabled();

    await page.reload();
    await expect(page).toHaveURL(`/?tab=output&run=${latestId}`);
    await expect(page.locator("header").getByText(latestId, { exact: true })).toBeVisible();
  });
}
