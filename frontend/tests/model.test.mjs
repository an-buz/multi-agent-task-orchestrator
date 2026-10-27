import test from "node:test";
import assert from "node:assert/strict";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import {
  appendRunEvent,
  applyStreamChunk,
  canRetryStep,
  dashboardInspectorStep,
  runSteps,
} from "../src/features/runs/model.ts";
import { graphErrors, inferType } from "../src/features/workflows/graph.ts";
import { agentSchema } from "../src/features/agents/form-schema.ts";
import { upsertItem, removeItem } from "../src/lib/collection.ts";
import { StatusBadge } from "../src/components/status-badge.tsx";

const step = { step_number: 1, status: "IN_PROGRESS", attempt: 2, output: "Partial" };
const run = { id: "run", plan: { summary: "Keep summary", steps: [step] } };
const chunk = (output, attempt = 2) => ({
  event: "agent:stream_chunk",
  data: { stepNumber: 1, output, attempt },
});

const activation = (stepNumber, id) => ({
  id: String(id),
  event: "agent:status_change",
  data: { stepNumber, status: "IN_PROGRESS" },
});

test("dashboard follows activation order rather than plan order or manual selection", () => {
  const steps = [1, 2, 3].map((step_number) => ({ step_number, status: "IN_PROGRESS" }));
  const run = { plan: { steps } };
  let log = { events: [], activityEvents: [], after: 0 };
  for (const [number, id] of [
    [3, 1],
    [1, 2],
    [2, 3],
  ]) {
    log = appendRunEvent(log, activation(number, id));
    assert.equal(dashboardInspectorStep(run, log.activationOrder, 3).step_number, number);
  }
  // Output from an older parallel step must not steal focus.
  log = appendRunEvent(log, chunk("Older agent still streaming"));
  assert.equal(dashboardInspectorStep(run, log.activationOrder).step_number, 2);
  steps[1].status = "COMPLETED";
  assert.equal(dashboardInspectorStep(run, log.activationOrder).step_number, 1);
  steps[0].status = "FAILED";
  assert.equal(dashboardInspectorStep(run, log.activationOrder).step_number, 3);
  steps[2].status = "COMPLETED";
  assert.equal(dashboardInspectorStep(run, log.activationOrder).step_number, 2);
  assert.equal(dashboardInspectorStep(run, log.activationOrder, 1).step_number, 1);
  steps[0].status = "IN_PROGRESS";
  log = appendRunEvent(log, activation(1, 4));
  assert.equal(dashboardInspectorStep(run, log.activationOrder).step_number, 1);
});

test("activation order survives eviction, duplicates, stale replay and non-activation events", () => {
  let log = { events: [], activityEvents: [], after: 0 };
  log = appendRunEvent(appendRunEvent(log, activation(2, 1)), activation(1, 2));
  for (let id = 3; id <= 203; id++)
    log = appendRunEvent(log, { id: String(id), event: "agent:tool_result" });
  for (const event of [
    activation(2, 1),
    { ...activation(2, 204), data: { stepNumber: 2, status: "COMPLETED" } },
    { ...activation(2, 205), payload: {}, data: {} },
    activation(-1, 206),
  ])
    log = appendRunEvent(log, event);
  assert.deepEqual(log.activationOrder, [2, 1]);
  const retry = activation(2, 207);
  log = appendRunEvent(appendRunEvent(log, retry), retry);
  assert.deepEqual(log.activationOrder, [1, 2]);
});

test("inspector handles empty runs, legacy plans, snapshots and separate run histories", () => {
  assert.equal(dashboardInspectorStep(undefined, []), undefined);
  assert.equal(dashboardInspectorStep({ plan: [] }, [1]), undefined);
  const steps = [
    { step_number: 1, status: "FAILED" },
    { step_number: 2, status: "IN_PROGRESS" },
  ];
  assert.equal(dashboardInspectorStep({ plan: steps }, [], 1), steps[1]);
  steps[1].status = "PENDING";
  assert.equal(dashboardInspectorStep({ plan: steps }, []), steps[0]);
  let log = { events: [], activityEvents: [], after: 0 };
  log = appendRunEvent(log, {
    ...activation(2, 1),
    data: undefined,
    payload: activation(2, 1).data,
  });
  assert.equal(dashboardInspectorStep({ plan: steps }, log.activationOrder), steps[1]);
  assert.equal(dashboardInspectorStep({ plan: steps }, []), steps[0]);
});

test("retry is available only for a failed step in a failed run without a retryable flag", () => {
  for (const status of [
    "PLANNING",
    "AWAITING_CONFIRMATION",
    "IN_PROGRESS",
    "FAILED",
    "CANCELLED",
    "COMPLETED",
  ]) {
    for (const stepStatus of ["PENDING", "IN_PROGRESS", "FAILED", "CANCELLED", "COMPLETED"]) {
      assert.equal(
        canRetryStep({ status }, { status: stepStatus }),
        status === "FAILED" && stepStatus === "FAILED",
      );
    }
  }
});

test("long streams preserve activity history and advance replay independently", () => {
  let log = { events: [], activityEvents: [], after: 0 };
  const started = { id: "1", event: "task:started" };
  const tool = { id: "2", event: "agent:tool_call" };
  log = appendRunEvent(appendRunEvent(log, started), tool);
  for (let id = 3; id <= 203; id++)
    log = appendRunEvent(log, { ...chunk(String(id)), id: String(id) });
  assert.equal(log.events.length, 150);
  assert.deepEqual(log.activityEvents, [started, tool]);
  assert.equal(log.after, 203);
  log = appendRunEvent(log, started);
  assert.equal(log.activityEvents.length, 2);
  assert.equal(log.after, 203);
  for (let id = 204; id <= 404; id++)
    log = appendRunEvent(log, { id: String(id), event: "agent:status_change" });
  assert.equal(log.events.length, 150);
  assert.equal(log.activityEvents.length, 150);
  assert.equal(log.after, 404);
});

test("stream output is absolute and duplicate delivery is idempotent", () => {
  const updated = applyStreamChunk(run, chunk("Привет 🌍"));
  assert.equal(runSteps(updated)[0].output, "Привет 🌍");
  assert.equal(updated.plan.summary, "Keep summary");
  assert.equal(applyStreamChunk(updated, chunk("Привет 🌍")), updated);
  assert.equal(step.output, "Partial");
});

test("older attempts cannot overwrite a newer response", () => {
  assert.equal(applyStreamChunk(run, chunk("stale", 1)), run);
});

for (const status of ["COMPLETED", "FAILED", "CANCELLED"]) {
  test(`replayed chunks cannot reopen ${status} steps`, () => {
    const terminal = { ...run, plan: { steps: [{ ...step, status }] } };
    assert.equal(applyStreamChunk(terminal, chunk("stale")), terminal);
    assert.equal(
      runSteps(applyStreamChunk(terminal, chunk("new attempt", 3)))[0].status,
      "IN_PROGRESS",
    );
  });
}

test("retry reset clears output and preserves legacy array plans", () => {
  const reset = applyStreamChunk({ ...run, plan: [step] }, chunk("", 3));
  assert.ok(Array.isArray(reset.plan));
  assert.equal(runSteps(reset)[0].output, "");
});

test("malformed stream payloads and missing plans are ignored", () => {
  for (const data of [
    {},
    { stepNumber: 1, output: 2, attempt: 2 },
    { stepNumber: 1, output: "bad", attempt: -1 },
  ]) {
    assert.equal(applyStreamChunk(run, { event: "agent:stream_chunk", data }), run);
  }
  assert.equal(applyStreamChunk(undefined, chunk("x")), undefined);
});

test("collection counters account for create, update, repeated delete and absent cache", () => {
  const initial = { items: [{ id: "1", name: "Old" }], total: 1 };
  const created = upsertItem(initial, { id: "2", name: "New" });
  assert.equal(created.total, 2);
  const edited = upsertItem(created, { id: "1", name: "Edited" });
  assert.equal(edited.total, 2);
  assert.deepEqual(
    edited.items.map((item) => item.id),
    ["2", "1"],
  );
  const removed = removeItem(edited, "1");
  assert.equal(removeItem(removed, "1").total, 1);
  assert.equal(upsertItem(undefined, { id: "1" }), undefined);
  assert.equal(removeItem(undefined, "1"), undefined);
});

const nodes = [1, 2, 3].map((step) => ({ id: String(step), data: { step } }));
const edge = (source, target) => ({ source: String(source), target: String(target) });
test("workflow inference covers sequential, parallel aggregator and hybrid graphs", () => {
  assert.equal(inferType(nodes, [edge(1, 2), edge(2, 3)]), "sequential");
  assert.equal(inferType(nodes, [edge(1, 3), edge(2, 3)]), "parallel");
  assert.equal(inferType(nodes, [edge(1, 2), edge(1, 3)]), "hybrid");
});

test("graph validation allows independent branches and rejects empty, cyclic and dangling graphs", () => {
  assert.ok(graphErrors([], []).length);
  assert.deepEqual(graphErrors(nodes, [edge(1, 2)]), []);
  assert.deepEqual(graphErrors(nodes, []), []);
  assert.equal(inferType(nodes, []), "parallel");
  assert.equal(inferType(nodes, [edge(1, 2)]), "hybrid");
  assert.ok(
    graphErrors(nodes, [edge(1, 2), edge(2, 3), edge(3, 1)]).some((error) =>
      error.includes("cycle"),
    ),
  );
  assert.ok(
    graphErrors(nodes, [edge(1, 99), edge(99, 2)]).some((error) => error.includes("existing")),
  );
  assert.deepEqual(graphErrors(nodes, [edge(1, 2), edge(2, 3)]), []);
});

test("agent form schema trims text and rejects invalid values", () => {
  const agent = {
    name: " Reviewer ",
    role: "Review",
    system_prompt: "Review code",
    model: "mock",
    temperature: 0.5,
    max_tokens: 100,
    context_window: 1000,
    tools: [],
  };
  assert.equal(agentSchema.parse(agent).name, "Reviewer");
  for (const invalid of [
    { name: " " },
    { temperature: 2 },
    { max_tokens: 1.5 },
    { context_window: 0 },
    { max_tokens: 1000 },
  ]) {
    assert.equal(agentSchema.safeParse({ ...agent, ...invalid }).success, false);
  }
});

for (const [status, token] of [
  ["PENDING", "pending"],
  ["IN_PROGRESS", "progress"],
  ["COMPLETED", "completed"],
  ["FAILED", "failed"],
  ["CANCELLED", "pending"],
  ["PLANNING", "progress"],
  ["AWAITING_CONFIRMATION", "pending"],
  ["PAUSED", "warning"],
  ["UNAVAILABLE", "warning"],
]) {
  test(`StatusBadge renders ${status} with its semantic color and indicator`, () => {
    const html = renderToStaticMarkup(createElement(StatusBadge, { status }));
    assert.ok(html.endsWith(`>${status}</span>`));
    assert.ok(html.includes(`style="color:var(--status-${token})"`));
    assert.match(html, /<span class="[^"]*rounded-full[^\"]*bg-current[^\"]*"><\/span>/);
  });
}

for (const [status, label, tone] of [
  ["COMPLETED", "Completed", "text-status-completed"],
  ["IN_PROGRESS", "In Progress", "text-status-warning"],
  ["PLANNING", "Planning", "text-status-warning"],
  ["FAILED", "Failed", "text-destructive"],
  ["PENDING", "Pending", "text-muted-foreground"],
  ["CANCELLED", "Cancelled", "text-muted-foreground"],
  ["AWAITING_CONFIRMATION", "Awaiting Confirmation", "text-muted-foreground"],
  ["PAUSED", "Paused", "text-muted-foreground"],
  ["UNAVAILABLE", "Unavailable", "text-muted-foreground"],
]) {
  test(`pipeline StatusBadge renders ${status} with its readable label and tone`, () => {
    const html = renderToStaticMarkup(createElement(StatusBadge, { status, variant: "pipeline" }));
    assert.ok(html.endsWith(`>${label}</span>`));
    assert.match(html, new RegExp(`class="[^"]*\\b${tone}\\b[^"]*"`));
    assert.match(html, /<i class="[^"]*rounded-full[^\"]*bg-current[^\"]*"><\/i>/);
  });
}
