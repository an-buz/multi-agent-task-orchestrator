import { expect, test } from "@playwright/test";

for (const theme of ["dark", "light"]) {
  test(`run deletion confirmation, errors, and active protection in ${theme}`, async ({ page }) => {
    await page.addInitScript((value) => localStorage.setItem("theme", value), theme);
    const completedId = "00000000-0000-4000-8000-000000000020";
    const activeId = "00000000-0000-4000-8000-000000000021";
    let deletes = 0;
    let deleted = false;
    let finishDeletion: (() => void) | undefined;
    const summaries = [
      { id: completedId, task: "Finished review", status: "COMPLETED" },
      { id: activeId, task: "Active review", status: "IN_PROGRESS" },
    ].map((run) => ({
      ...run, workflow_id: "00000000-0000-4000-8000-000000000010",
      workflow_title: "Review workflow", created_at: "2026-10-09T12:00:00Z", total_tokens: 10,
    }));
    await page.route("**/api/v1/**", async (route) => {
      const request = route.request();
      const headers = { "access-control-allow-origin": "http://localhost:3000" };
      if (request.method() === "OPTIONS") {
        return route.fulfill({ status: 204, headers: {
          ...headers, "access-control-allow-methods": "GET,DELETE,OPTIONS",
          "access-control-allow-headers": "content-type",
        } });
      }
      if (request.method() === "DELETE") {
        expect(new URL(request.url()).pathname).toBe(`/api/v1/runs/${completedId}`);
        deletes += 1;
        if (deletes === 1) return route.fulfill({ status: 409, headers,
          json: { error: { code: "invalid_run_state", message: "Cancel this run before deleting it." } },
        });
        await new Promise<void>((resolve) => { finishDeletion = resolve; });
        deleted = true;
        return route.fulfill({ status: 204, headers });
      }
      return route.fulfill({ headers, json: {
        items: deleted ? summaries.slice(1) : summaries, total: deleted ? 1 : 2,
      } });
    });
    await page.goto("/runs");
    const deleteButton = page.getByRole("button", { name: `Delete run ${completedId}`, exact: true });
    await expect(page.getByRole("button", { name: `Delete run ${activeId}`, exact: true })).toBeDisabled();
    await deleteButton.click();
    const dialog = page.getByRole("alertdialog");
    await expect(dialog).toContainText("results, steps, and event history");
    await dialog.getByRole("button", { name: "Cancel", exact: true }).click();
    expect(deletes).toBe(0);
    await deleteButton.click();
    await dialog.getByRole("button", { name: "Delete run", exact: true }).click();
    await expect(dialog.getByRole("alert")).toHaveText("Cancel this run before deleting it.");
    await dialog.getByRole("button", { name: "Delete run", exact: true }).click();
    await expect(dialog.getByRole("button", { name: "Deleting…", exact: true })).toBeDisabled();
    await expect(dialog.getByRole("button", { name: "Cancel", exact: true })).toBeDisabled();
    await expect.poll(() => typeof finishDeletion).toBe("function");
    finishDeletion!();
    await expect(dialog).not.toBeVisible();
    await expect(page.getByText("Finished review", { exact: true })).toHaveCount(0);
    await expect(page.getByText("Active review", { exact: true })).toBeVisible();
    expect(deletes).toBe(2);
    await page.reload();
    await expect(page.getByText("Finished review", { exact: true })).toHaveCount(0);
    await expect(page.getByText("Active review", { exact: true })).toBeVisible();
  });
}
