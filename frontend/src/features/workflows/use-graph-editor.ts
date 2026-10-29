"use client";

import { useRef, useState } from "react";
import { useNodesState, useEdgesState, type Edge } from "@xyflow/react";

import type { AgentNode } from "./graph";

export function useGraphEditor() {
  const [nodes, setNodes, onNodesChange] = useNodesState<AgentNode>([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([]);

  const undoStack = useRef<Array<{ nodes: AgentNode[]; edges: Edge[] }>>([]);
  const redoStack = useRef<Array<{ nodes: AgentNode[]; edges: Edge[] }>>([]);

  const [canUndo, setCanUndo] = useState(false);
  const [canRedo, setCanRedo] = useState(false);

  function rememberGraph() {
    undoStack.current.push({ nodes, edges });

    if (undoStack.current.length > 50) undoStack.current.shift();

    redoStack.current = [];
    setCanUndo(true);
    setCanRedo(false);
  }

  function undoGraph() {
    const previous = undoStack.current.pop();

    if (!previous) return;

    redoStack.current.push({ nodes, edges });
    setNodes(previous.nodes);
    setEdges(previous.edges);
    setCanUndo(undoStack.current.length > 0);
    setCanRedo(true);
  }

  function redoGraph() {
    const next = redoStack.current.pop();

    if (!next) return;

    undoStack.current.push({ nodes, edges });
    setNodes(next.nodes);
    setEdges(next.edges);
    setCanUndo(true);
    setCanRedo(redoStack.current.length > 0);
  }

  function autoLayout() {
    rememberGraph();

    const remaining = new Map(
      nodes.map((node) => [node.id, edges.filter((edge) => edge.target === node.id).length]),
    );
    const levels = new Map<string, number>();

    const queue = [...remaining].filter(([, count]) => count === 0).map(([id]) => id);

    while (queue.length) {
      const id = queue.shift();

      if (!id) continue;

      for (const edge of edges.filter((item) => item.source === id)) {
        levels.set(edge.target, Math.max(levels.get(edge.target) ?? 0, (levels.get(id) ?? 0) + 1));

        const count = (remaining.get(edge.target) ?? 1) - 1;

        remaining.set(edge.target, count);

        if (count === 0) queue.push(edge.target);
      }
    }

    const offsets = new Map<number, number>();

    setNodes(
      nodes.map((node) => {
        const level = levels.get(node.id) ?? 0;
        const row = offsets.get(level) ?? 0;

        offsets.set(level, row + 1);

        return { ...node, position: { x: 90 + level * 280, y: 80 + row * 170 } };
      }),
    );
  }

  function resetHistory() {
    undoStack.current = [];
    redoStack.current = [];
    setCanUndo(false);
    setCanRedo(false);
  }

  return {
    nodes,
    setNodes,
    onNodesChange,
    edges,
    setEdges,
    onEdgesChange,
    rememberGraph,
    undoGraph,
    redoGraph,
    autoLayout,
    resetHistory,
    canUndo,
    canRedo,
  };
}
