import test from "node:test";
import assert from "node:assert/strict";
import { agentSchemaForModels, modelTokenLimits } from "../src/features/agents/form-schema.ts";
import { planFormValues, samePlanTasks } from "../src/features/runs/plan-schema.ts";
import { confirmRun, editRunPlan } from "../src/features/runs/api.ts";

const model = {
  key: "gpt-4o",
  context_window: 128000,
  max_output_tokens: 16384,
};
const agent = {
  name: "Reviewer",
  role: "Review",
  system_prompt: "Review changes",
  model: model.key,
  temperature: 0.7,
  max_tokens: 20000,
  context_window: 200000,
  tools: [],
};

test("switching model respects output and context limits and leaves room for input", () => {
  const limits = modelTokenLimits(agent, model);
  assert.deepEqual(limits, { context_window: 128000, max_tokens: 16384 });
  assert.equal(agentSchemaForModels([model]).safeParse({ ...agent, ...limits }).success, true);
  assert.equal(modelTokenLimits({ ...agent, context_window: 8000 }, model).max_tokens, 7999);
});

test("manual token edits are rejected above model output and context limits", () => {
  const schema = agentSchemaForModels([model]);
  const invalid = schema.safeParse({ ...agent, context_window: 128000 });
  assert.equal(invalid.success, false);
  assert.equal(invalid.error.issues[0].path[0], "max_tokens");
  const invalidContext = schema.safeParse({ ...agent, max_tokens: 4096 });
  assert.equal(invalidContext.success, false);
  assert.equal(invalidContext.error.issues[0].path[0], "context_window");
  assert.equal(schema.safeParse({ ...agent, model: "disabled" }).success, false);
});

test("plan review detects remote edits, missing steps and step renumbering", () => {
  const original = planFormValues([{ step_number: 1, subtask: "Original" }]);
  const refreshed = planFormValues([{ step_number: 1, subtask: "Updated remotely" }]);
  assert.equal(samePlanTasks(original.expected_subtasks, refreshed.expected_subtasks), false);
  assert.equal(samePlanTasks(original.expected_subtasks, {}), false);
  assert.equal(samePlanTasks(original.expected_subtasks, { 2: "Original" }), false);
  assert.equal(samePlanTasks(original.expected_subtasks, { 1: "Original" }), true);
});

test("plan save and confirmation send their own reviewed task snapshots", async (t) => {
  const requests = [];
  t.mock.method(globalThis, "fetch", async (_url, options) => {
    requests.push(JSON.parse(options.body));
    return Response.json({ id: "run" });
  });
  const steps = [{ step_number: 1, subtask: "Edited" }];
  await editRunPlan("run", steps, { 1: "Original" });
  await confirmRun("run", { 1: "Edited" });
  assert.deepEqual(requests, [
    { steps, expected_subtasks: { 1: "Original" } },
    { expected_subtasks: { 1: "Edited" } },
  ]);
});
