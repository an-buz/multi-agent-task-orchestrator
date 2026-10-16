import type { Node, Edge } from "@xyflow/react";
import type { WorkflowType } from "./types";

export type AgentNodeData = {
  agentId: string;
  label: string;
  role: string;
  model: string;
  step: number;
  inputTransform: string;
};
export type AgentNode = Node<AgentNodeData>;

export function inferType(nodes: AgentNode[], edges: Edge[]): WorkflowType {
  const ordered = [...nodes].sort((left, right) => left.data.step - right.data.step);
  const incoming = new Map(
    ordered.map((node) => [
      node.data.step,
      edges
        .filter((edge) => edge.target === node.id)
        .map((edge) => Number(edge.source))
        .sort((left, right) => left - right),
    ]),
  );
  if (
    ordered.every(
      (node, index) =>
        JSON.stringify(incoming.get(node.data.step)) ===
        JSON.stringify(index === 0 ? [] : [ordered[index - 1].data.step]),
    )
  )
    return "sequential";
  const aggregators = [...incoming].filter(([, dependencies]) => dependencies.length > 0);
  if (
    aggregators.length <= 1 &&
    (aggregators.length === 0 ||
      (aggregators[0][1].length === ordered.length - 1 &&
        aggregators[0][1].every((step) => step !== aggregators[0][0])))
  )
    return "parallel";
  return "hybrid";
}

export function graphErrors(nodes: AgentNode[], edges: Edge[]): string[] {
  const errors: string[] = [];
  if (!nodes.length) errors.push("Add at least one agent to the workflow.");
  const ids = new Set(nodes.map((node) => node.id));
  if (edges.some((edge) => !ids.has(edge.source) || !ids.has(edge.target))) {
    errors.push("Every edge must reference existing nodes.");
    return errors;
  }
  const remaining = new Map(
    nodes.map((node) => [node.id, edges.filter((edge) => edge.target === node.id).length]),
  );
  const ready = [...remaining].filter(([, count]) => count === 0).map(([id]) => id);
  let visited = 0;
  while (ready.length) {
    const id = ready.pop();
    if (!id) continue;
    visited += 1;
    edges
      .filter((edge) => edge.source === id)
      .forEach((edge) => {
        const count = (remaining.get(edge.target) ?? 0) - 1;
        remaining.set(edge.target, count);
        if (count === 0) ready.push(edge.target);
      });
  }
  if (visited !== nodes.length) errors.push("The graph contains a cycle.");
  return errors;
}
