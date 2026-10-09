import { expect, test } from "@playwright/test";

const runId = "00000000-0000-4000-8000-000000000020";
const agentId = "00000000-0000-4000-8000-000000000001";

for (const theme of ["dark", "light"]) {
  test(`mock streaming, retry reset and snapshot recovery in ${theme}`, async ({ page }) => {
    await page.addInitScript((value) => {
      localStorage.setItem("theme", value);
      class MockEventSource extends EventTarget {
        onerror = null;
        forward = (event: Event) => {
          const envelope = (event as CustomEvent).detail;
          this.dispatchEvent(new MessageEvent(envelope.event, {
            data: JSON.stringify(envelope),
          }));
        };
        constructor() {
          super();
          window.addEventListener("mock-sse", this.forward);
        }
        close() { window.removeEventListener("mock-sse", this.forward); }
      }
      Object.defineProperty(window, "EventSource", { value: MockEventSource });
    }, theme);

    let output = "";
    let completed = false;
    let gets = 0;
    await page.route("**/api/v1/**", async (route) => {
      const headers = { "access-control-allow-origin": "http://localhost:3000" };
      const pathname = new URL(route.request().url()).pathname;
      if (pathname === `/api/v1/runs/${runId}`) {
        gets += 1;
        return route.fulfill({ headers, json: {
          id: runId, workflow_id: agentId, task: "Mock streaming QA",
          status: completed ? "COMPLETED" : "IN_PROGRESS",
          created_at: "2026-10-09T12:00:00Z", total_tokens: completed ? 28 : 0,
          final_report: completed ? "Fixture result" : null,
          plan: { summary: "Mock plan", steps: [{
            agent_id: agentId, agent_name: "Reviewer", step_number: 1,
            depends_on: [], attempt: 1,
            status: completed ? "COMPLETED" : "IN_PROGRESS", output,
          }] },
        } });
      }
      return route.fulfill({ headers, json: { items: [], total: 0 } });
    });
    const emit = async (text: string, reset = false) => {
      output = text;
      await page.evaluate(({ text, reset, agentId }) => {
        window.dispatchEvent(new CustomEvent("mock-sse", { detail: {
          event: "agent:stream_chunk", data: {
            agentId, stepNumber: 1, textDelta: text, output: text, reset, attempt: 1,
          },
        } }));
      }, { text, reset, agentId });
    };

    await page.goto(`/runs/${runId}`);
    await expect(page.getByRole("heading", { name: "Execution steps" })).toBeVisible();
    await expect(page.getByText("Generating response…")).toBeVisible();
    const initialGets = gets;
    await emit("Привет 🌍");
    await expect(page.getByLabel("Output for step 1")).toHaveText("Привет 🌍");
    await emit("Привет 🌍");
    await expect(page.getByLabel("Output for step 1")).toHaveText("Привет 🌍");
    expect(gets).toBe(initialGets);
    await emit("", true);
    await expect(page.getByLabel("Output for step 1")).toHaveCount(0);
    await emit("Fixture ");
    await page.reload();
    await expect(page.getByLabel("Output for step 1")).toHaveText("Fixture ");
    await emit("Fixture result");
    await expect(page.getByLabel("Output for step 1")).toHaveText("Fixture result");
    completed = true;
    await page.evaluate(() => window.dispatchEvent(new CustomEvent("mock-sse", {
      detail: { event: "agent:completed", data: {} },
    })));
    await expect(page.getByRole("heading", { name: "Final report" })).toBeVisible();
    await expect(page.getByText("Generating response…")).toHaveCount(0);
    await emit("Old replay");
    await expect(page.getByLabel("Output for step 1")).toHaveText("Fixture result");
  });
}
