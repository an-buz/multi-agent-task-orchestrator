import { expect, test } from "@playwright/test";

test("HTTP 502 replaces EventSource using the last received cursor", async ({ page }) => {
  const id = "00000000-0000-4000-8000-000000000020";
  const connections: string[] = [];

  await page.route("**/api/v1/**", async (route) => {
    const url = new URL(route.request().url());
    const headers = { "access-control-allow-origin": "http://localhost:3000" };

    if (url.pathname.endsWith("/events")) {
      connections.push(url.search);

      if (connections.length === 2) {
        return route.fulfill({ headers, status: 502, body: "Unavailable" });
      }

      return route.fulfill({
        headers,
        contentType: "text/event-stream",
        body: 'id: 42\nevent: plan:ready\ndata: {"event":"plan:ready","data":{}}\n\n',
      });
    }

    if (url.pathname === `/api/v1/runs/${id}`) {
      return route.fulfill({
        headers,
        json: {
          id,
          status: "IN_PROGRESS",
          task: "Reconnect regression",
          created_at: "2026-11-04T12:00:00Z",
          total_tokens: 0,
          plan: [],
        },
      });
    }

    return route.fulfill({ headers, json: { items: [], total: 0 } });
  });

  await page.goto(`/runs/${id}`);
  await expect.poll(() => connections.length, { timeout: 20000 }).toBeGreaterThanOrEqual(3);
  expect(connections[2]).toBe("?after=42");
});
