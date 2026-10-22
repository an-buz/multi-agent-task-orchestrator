import assert from "node:assert/strict";
import test from "node:test";
import { consoleEvents, eventPresentation } from "../src/features/monitor/console-events.ts";
import { appendRunEvent } from "../src/features/runs/model.ts";

const steps = [{ step_number: 1, agent_name: "Demo Analyst" }];

test("console excludes response fragments and resets while preserving activity through long streams", () => {
  const status = {
    id: "1",
    event: "agent:status_change",
    data: { stepNumber: 1, status: "IN_PROGRESS" },
  };
  let log = appendRunEvent({ events: [], activityEvents: [], after: 0 }, status);
  for (let id = 2; id <= 502; id++) {
    log = appendRunEvent(log, {
      id: String(id),
      event: "agent:stream_chunk",
      data: { reset: id === 2, textDelta: "broken frag", output: "Full output" },
    });
  }
  assert.deepEqual(consoleEvents([status, ...log.events]), [status]);
  assert.deepEqual(consoleEvents(log.activityEvents), [status]);
  assert.equal(eventPresentation(status, steps).message, "Demo Analyst: in progress.");
});

test("console normalizes multiline summaries and agent names into one readable line", () => {
  const result = eventPresentation(
    {
      event: "agent:tool_result",
      data: { toolName: "file_reader", summary: " Read\n  3 files.\tDone. " },
    },
    steps,
  );
  assert.equal(result.message, "Read 3 files. Done.");
  assert.equal(result.tag, "Tool: file_reader");
  assert.equal(
    eventPresentation(
      { event: "agent:status_change", data: { stepNumber: 1, status: "COMPLETED" } },
      [{ step_number: 1, agent_name: "Demo\nAnalyst" }],
    ).tag,
    "Agent: Demo Analyst",
  );
});

test("console presents lifecycle, tool calls and failures without raw JSON payloads", () => {
  for (const event of [
    "task:paused",
    "task:resumed",
    "task:failed",
    "task:cancelled",
    "run:snapshot",
    "decision:required",
    "decision:resolved",
  ]) {
    const result = eventPresentation({ event, data: { taskId: "internal-id" } }, steps);
    assert.ok(result.message.length > 10);
    assert.ok(!result.message.includes("internal-id"));
    assert.ok(!result.message.includes("{"));
  }
  assert.equal(
    eventPresentation(
      { event: "agent:tool_call", data: { stepNumber: 1, toolName: "calculator" } },
      steps,
    ).message,
    "Demo Analyst is calling calculator.",
  );
  assert.equal(
    eventPresentation(
      { event: "agent:failed", payload: { stepNumber: 1, error: { message: "Timed\nout." } } },
      steps,
    ).message,
    "Demo Analyst failed. Timed out.",
  );
});
