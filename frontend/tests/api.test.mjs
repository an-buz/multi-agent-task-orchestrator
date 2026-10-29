import test from "node:test";
import assert from "node:assert/strict";

import { apiRequest, apiResponse, apiUrl, ApiError } from "../src/lib/api.ts";
import { waitForRunPlan, subscribeToRun } from "../src/features/runs/api.ts";

import { QueryClient } from "@tanstack/react-query";

import { getRun } from "../src/features/runs/api.ts";

test("API URL has exactly one boundary slash", () => {
  assert.match(apiUrl("//agents"), /\/api\/v1\/agents$/);
});

test("JSON and multipart headers, no-content responses and cancellation", async (t) => {
  const controller = new AbortController();
  let init;

  t.mock.method(globalThis, "fetch", async (_url, options) => {
    init = options;
    return new Response(null, { status: 204 });
  });

  assert.equal(
    await apiRequest("/agents", { method: "POST", body: "{}", signal: controller.signal }),
    undefined,
  );

  assert.equal(init.headers.get("content-type"), "application/json");
  assert.equal(init.signal, controller.signal);

  await apiRequest("/files", { method: "POST", body: new FormData() });

  assert.equal(init.headers.has("content-type"), false);
});

for (const [body, status, message] of [
  [
    { error: { code: "workflow_has_runs", message: "Delete runs first." } },
    409,
    "Delete runs first.",
  ],
  [
    { detail: [{ loc: ["body", "max_tokens"], msg: "Must be positive" }] },
    422,
    "max_tokens: Must be positive",
  ],
  [{ detail: "Missing run" }, 404, "Missing run"],
  [null, 500, "API request failed with status 500"],
]) {
  test(`API exposes ${status} errors including validation and export`, async (t) => {
    t.mock.method(globalThis, "fetch", async () => Response.json(body, { status }));

    await assert.rejects(
      apiResponse("/export"),
      (error) => error instanceof ApiError && error.status === status && error.message === message,
    );
  });
}

function mockBrowser(t) {
  const sources = [];

  class MockSource extends EventTarget {
    closed = false;

    constructor(url) {
      super();
      this.url = url;
      sources.push(this);
    }

    close() {
      this.closed = true;
    }
  }

  const previousWindow = Object.getOwnPropertyDescriptor(globalThis, "window");
  const previousSource = Object.getOwnPropertyDescriptor(globalThis, "EventSource");

  Object.defineProperty(globalThis, "window", { configurable: true, value: globalThis });
  Object.defineProperty(globalThis, "EventSource", { configurable: true, value: MockSource });

  t.after(() => {
    if (previousWindow) Object.defineProperty(globalThis, "window", previousWindow);
    else delete globalThis.window;

    if (previousSource) Object.defineProperty(globalThis, "EventSource", previousSource);
    else delete globalThis.EventSource;
  });

  return () => sources.at(-1);
}

test("subscription ignores malformed JSON and closes its listeners", (t) => {
  const source = mockBrowser(t);
  const received = [];
  const close = subscribeToRun(
    "run",
    (event) => received.push(event),
    () => {},
    { after: 12 },
  );

  assert.ok(source().url.endsWith("?after=12"));
  source().dispatchEvent(new MessageEvent("plan:ready", { data: "{broken" }));
  source().dispatchEvent(new MessageEvent("plan:ready", { data: "null" }));
  source().dispatchEvent(new MessageEvent("plan:ready", { data: "{}" }));

  source().dispatchEvent(
    new MessageEvent("plan:ready", {
      data: JSON.stringify({ event: "plan:ready" }),
      lastEventId: "13",
    }),
  );

  assert.equal(received[0].id, "13");
  close();
  assert.equal(source().closed, true);
  source().dispatchEvent(new MessageEvent("plan:ready", { data: "{}" }));
  assert.equal(received.length, 1);
});

test("cancelled detail queries cannot overwrite a newer SSE cache update", async (t) => {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const key = ["runs", "run"];
  let respond;
  let signal;

  t.mock.method(globalThis, "fetch", (_url, options) => {
    signal = options.signal;
    return new Promise((resolve) => {
      respond = resolve;
    });
  });

  const pending = client
    .fetchQuery({ queryKey: key, queryFn: ({ signal }) => getRun("run", signal) })
    .catch(() => undefined);

  await client.cancelQueries({ queryKey: key, exact: true });

  client.setQueryData(key, { output: "New streamed response" });
  respond(Response.json({ output: "Old HTTP response" }));

  await pending;
  await new Promise((resolve) => setImmediate(resolve));

  assert.equal(signal.aborted, true);
  assert.equal(client.getQueryData(key).output, "New streamed response");
  client.clear();
});

test("plan wait closes SSE immediately when a fast worker already finished", async (t) => {
  const source = mockBrowser(t);

  t.mock.method(globalThis, "fetch", async () =>
    Response.json({ status: "AWAITING_CONFIRMATION", plan: { steps: [] } }),
  );

  assert.equal((await waitForRunPlan("run")).status, "AWAITING_CONFIRMATION");
  assert.equal(source().closed, true);
});

test("plan wait cancellation closes SSE and aborts the pending HTTP request", async (t) => {
  const source = mockBrowser(t);
  let requestSignal;

  t.mock.method(globalThis, "fetch", (_url, { signal }) => {
    requestSignal = signal;
    return new Promise((_resolve, reject) =>
      signal.addEventListener("abort", () => reject(signal.reason), { once: true }),
    );
  });

  const controller = new AbortController();
  const waiting = waitForRunPlan("run", controller.signal);

  controller.abort();

  await assert.rejects(waiting, { name: "AbortError" });

  assert.equal(source().closed, true);
  assert.equal(requestSignal.aborted, true);
});

test("plan wait polls if SSE never delivers the ready event", async (t) => {
  const source = mockBrowser(t);
  let poll;

  t.mock.method(globalThis, "setInterval", (callback) => {
    poll = callback;
    return 123;
  });

  t.mock.method(globalThis, "clearInterval", () => {});

  let ready = false;

  t.mock.method(globalThis, "fetch", async () =>
    Response.json(
      ready
        ? { status: "AWAITING_CONFIRMATION", plan: { steps: [] } }
        : { status: "PLANNING", plan: null },
    ),
  );

  const waiting = waitForRunPlan("run");

  await new Promise((resolve) => setImmediate(resolve));

  ready = true;
  poll();

  await waiting;

  assert.equal(source().closed, true);
});
