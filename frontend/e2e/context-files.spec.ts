import { expect, test } from "@playwright/test";

const fileId = "00000000-0000-4000-8000-000000000030";
const workflowId = "00000000-0000-4000-8000-000000000010";
const runId = "00000000-0000-4000-8000-000000000020";

for (const theme of ["dark", "light"]) {
  test(`context upload, removal and run creation in ${theme}`, async ({ page }) => {
    await page.addInitScript((value) => localStorage.setItem("theme", value), theme);
    let submitted: Record<string, unknown> | undefined;
    let removed = false;
    await page.route("**/api/v1/**", async (route) => {
      const request = route.request();
      const pathname = new URL(request.url()).pathname;
      const headers = {
        "access-control-allow-origin": "http://localhost:3000",
        "access-control-allow-methods": "GET,POST,DELETE,OPTIONS",
        "access-control-allow-headers": "content-type",
      };
      if (request.method() === "OPTIONS") return route.fulfill({ status: 204, headers });
      if (pathname === "/api/v1/workflows") return route.fulfill({ headers, json: {
        items: [{ id: workflowId, title: "Files workflow", steps: [], execution_type: "sequential" }], total: 1,
      } });
      if (pathname === "/api/v1/files" && request.method() === "POST") {
        expect(request.headers()["content-type"]).toContain("multipart/form-data");
        if (request.postDataBuffer()?.toString().includes("invalid.json")) {
          return route.fulfill({ status: 422, headers, json: { error: { message: "The context file contains invalid JSON." } } });
        }
        return route.fulfill({ status: 201, headers, json: {
          id: fileId, filename: "brief.pdf", size_bytes: 7, media_type: "application/pdf", created_at: "2026-10-08T08:00:00Z",
        } });
      }
      if (pathname === `/api/v1/files/${fileId}` && request.method() === "DELETE") {
        removed = true;
        return route.fulfill({ status: 204, headers });
      }
      if (pathname === "/api/v1/runs" && request.method() === "POST") {
        submitted = request.postDataJSON() as Record<string, unknown>;
        return route.fulfill({ status: 201, headers, json: {
          id: runId, status: "AWAITING_CONFIRMATION", plan: { summary: "Review files", steps: [] },
        } });
      }
      return route.fulfill({ headers, json: { items: [], total: 0 } });
    });
    await page.goto("/");
    await page.getByRole("button", { name: "Paste text" }).click();
    await page.getByPlaceholder("Paste context here...").fill("Keep this note");
    const input = page.locator('input[type="file"]');
    await expect(input).toHaveAttribute("accept", /application\/pdf/);
    const brief = { name: "brief.pdf", mimeType: "application/pdf", buffer: Buffer.from("%PDF-mock") };
    await input.setInputFiles(brief);
    await expect(page.getByRole("button", { name: "Remove attachment brief.pdf" })).toBeVisible();
    await expect(page.getByPlaceholder("Paste context here...")).toHaveValue("Keep this note");
    await page.getByRole("button", { name: "Remove attachment brief.pdf" }).click();
    await expect(page.getByRole("button", { name: "Remove attachment brief.pdf" })).toHaveCount(0);
    expect(removed).toBe(true);
    await expect(page.getByPlaceholder("Paste context here...")).toHaveValue("Keep this note");
    await input.setInputFiles({ name: "invalid.json", mimeType: "application/json", buffer: Buffer.from("{bad}") });
    await expect(page.getByRole("alert").filter({ hasText: "invalid JSON" })).toBeVisible();
    await input.setInputFiles(brief);
    await expect(page.getByRole("button", { name: "Remove attachment brief.pdf" })).toBeVisible();
    await page.getByRole("combobox", { name: "Workflow", exact: true }).click();
    await page.getByRole("option", { name: "Files workflow" }).click();
    await page.getByRole("button", { name: "Decompose and Run" }).click();
    await expect(page.getByRole("dialog", { name: "Plan preview" })).toBeVisible();
    expect(submitted?.file_ids).toEqual([fileId]);
    expect(submitted?.context_text).toBe("Keep this note");
  });
}
