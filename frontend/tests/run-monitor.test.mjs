import assert from "node:assert/strict";
import { registerHooks } from "node:module";
import test from "node:test";

const state = {
  items: [],
  params: new URLSearchParams("tab=output"),
  effects: [],
  navigations: [],
  subscriptions: [],
};

globalThis.__runMonitorTest = state;

const mocks = {
  react: "export const useEffect = (fn) => globalThis.__runMonitorTest.effects.push(fn);",
  "next/navigation": `
    export const usePathname = () => '/';
    export const useSearchParams = () => globalThis.__runMonitorTest.params;
    export const useRouter = () => ({ replace: (url, options) => {
      globalThis.__runMonitorTest.navigations.push({ url, options });
    }});
  `,
  "@/features/runs/queries": `
    export const useRuns = () => ({ data: { items: globalThis.__runMonitorTest.items } });
  `,
  "@/features/runs/use-run-events": `
    export const useRunEvents = (id) => {
      globalThis.__runMonitorTest.subscriptions.push(id);
      return { query: { data: { id } } };
    };
  `,
};

registerHooks({
  resolve(specifier, context, nextResolve) {
    if (specifier in mocks) {
      return {
        url: `data:text/javascript,${encodeURIComponent(mocks[specifier])}`,
        shortCircuit: true,
      };
    }

    return nextResolve(specifier, context);
  },
});

const { useRunMonitor } = await import("../src/features/monitor/use-run-monitor.ts");

function RenderMonitor() {
  state.effects = [];

  const monitor = useRunMonitor(state.params.get("run"));

  state.effects.forEach((effect) => effect());

  return monitor;
}

test("automatic selection pins the URL and completion never switches the subscription", () => {
  state.items = [{ id: "a", status: "IN_PROGRESS" }];

  assert.equal(RenderMonitor().runId, undefined);
  assert.equal(state.subscriptions.at(-1), undefined);
  assert.deepEqual(state.navigations.pop(), {
    url: "/?tab=output&run=a",
    options: { scroll: false },
  });

  state.params.set("run", "a");
  assert.equal(RenderMonitor().runId, "a");

  state.items = [
    { id: "b", status: "IN_PROGRESS" },
    { id: "a", status: "COMPLETED" },
  ];

  const monitor = RenderMonitor();

  assert.equal(monitor.runId, "a");
  assert.equal(state.subscriptions.at(-1), "a");
  assert.equal(state.navigations.length, 0);

  monitor.followLatestRun();
  assert.equal(state.navigations.pop().url, "/?tab=output&run=b");

  state.params.set("run", "b");
  assert.equal(RenderMonitor().runId, "b");

  state.items = [];
  assert.equal(RenderMonitor().runId, "b");
  assert.equal(state.navigations.length, 0);
});

test("empty initial list waits for data and falls back to the newest completed run", () => {
  state.params = new URLSearchParams();
  state.items = [];

  assert.equal(RenderMonitor().runId, undefined);
  assert.equal(state.navigations.length, 0);

  state.items = [{ id: "completed", status: "COMPLETED" }];
  RenderMonitor();

  assert.equal(state.navigations.pop().url, "/?run=completed");
});
