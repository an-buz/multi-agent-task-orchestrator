import test from "node:test";
import assert from "node:assert/strict";

import { graphSnapshot } from "../src/features/workflows/graph.ts";

const node = {
  id: "1",
  position: { x: 10, y: 20 },
  data: { agentId: "a", step: 1, inputTransform: "", label: "Agent" },
};
const snapshot = (title = "Draft", nodes = [node], edges = []) =>
  graphSnapshot(title, nodes, edges);

test("workflow dirty snapshot ignores React Flow selection and dimensions", () => {
  assert.equal(
    snapshot(),
    snapshot("Draft", [{ ...node, selected: true, measured: { width: 100, height: 50 } }]),
  );
});

test("workflow dirty snapshot detects title, nodes, position, input and connections", () => {
  for (const changed of [
    snapshot("Renamed"),
    snapshot("Draft", []),
    snapshot("Draft", [{ ...node, position: { x: 30, y: 20 } }]),
    snapshot("Draft", [{ ...node, data: { ...node.data, inputTransform: "New input" } }]),
    snapshot("Draft", [node], [{ source: "1", target: "2" }]),
  ])
    assert.notEqual(snapshot(), changed);
});

test("undoing graph edits restores the original snapshot", () => {
  assert.equal(snapshot(), snapshot("Draft", [structuredClone(node)]));
});
