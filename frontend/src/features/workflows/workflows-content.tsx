"use client";

import { useMemo, useState } from "react";
import { addEdge, Background, Controls, MiniMap, ReactFlow, type Connection } from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { GitBranch, LoaderCircle, Pencil, Plus, Save, Trash2, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { DeleteConfirmationDialog } from "@/components/delete-confirmation-dialog";
import { Dialog, DialogContent, DialogTitle } from "@/components/ui/dialog";
import { Textarea } from "@/components/ui/textarea";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectTrigger,
} from "@/components/ui/select";
import { AppShell } from "@/components/app-shell";
import { useAgents } from "@/features/agents/queries";
import { useDeleteWorkflow, useSaveWorkflow, useWorkflows } from "@/features/workflows/queries";

import type { Workflow, WorkflowInput, WorkflowType } from "./types";

import { useGraphEditor } from "./use-graph-editor";
import { inferType, graphErrors, type AgentNode } from "./graph";

export default function WorkflowsContent() {
  const workflowsQuery = useWorkflows();
  const agentsQuery = useAgents();
  const saveMutation = useSaveWorkflow();
  const deleteMutation = useDeleteWorkflow();
  const [deleting, setDeleting] = useState<Workflow | null>(null);
  const [editing, setEditing] = useState<Workflow | null>(null);
  const [editorOpen, setEditorOpen] = useState(false);
  const [title, setTitle] = useState("");
  const [preset, setPreset] = useState<WorkflowType>("hybrid");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [notice, setNotice] = useState("");
  const {
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
  } = useGraphEditor();
  const agents = agentsQuery.data?.items ?? [];
  const selected = nodes.find((node) => node.id === selectedId);
  const errors = useMemo(() => graphErrors(nodes, edges), [nodes, edges]);
  const executionType = useMemo(() => inferType(nodes, edges), [nodes, edges]);
  const onConnect = (connection: Connection) => {
    rememberGraph();
    setEdges((current) => addEdge(connection, current));
  };

  function openEditor(workflow?: Workflow) {
    setEditorOpen(true);
    setEditing(workflow ?? null);
    setTitle(workflow?.title ?? "");
    setPreset(workflow?.execution_type ?? "hybrid");
    const agentMap = new Map(agents.map((agent) => [agent.id, agent]));
    const nextNodes: AgentNode[] = (workflow?.steps ?? []).map((step, index) => {
      const agent = agentMap.get(step.agent_id);
      return {
        id: String(step.step_number),
        type: "default",
        position: workflow?.graph_layout[String(step.step_number)] ?? {
          x: 80 + (index % 3) * 260,
          y: 80 + Math.floor(index / 3) * 170,
        },
        data: {
          agentId: step.agent_id,
          label: agent?.name ?? "Unknown agent",
          role: agent?.role ?? "",
          model: agent?.model ?? "",
          step: step.step_number,
          inputTransform: step.input_transform,
        },
      };
    });
    setNodes(nextNodes);
    setEdges(
      (workflow?.steps ?? []).flatMap((step) =>
        step.depends_on.map((dep) => ({
          id: `${dep}-${step.step_number}`,
          source: String(dep),
          target: String(step.step_number),
          type: "smoothstep",
          animated: false,
        })),
      ),
    );
    setSelectedId(null);
    resetHistory();
    setNotice("");
  }

  function addAgent(agentId: string) {
    const agent = agents.find((item) => item.id === agentId);
    if (!agent) return;
    const step = Math.max(0, ...nodes.map((node) => node.data.step)) + 1;
    rememberGraph();
    setNodes((current) => [
      ...current,
      {
        id: String(step),
        type: "default",
        position: { x: 100 + ((step - 1) % 3) * 260, y: 100 + Math.floor((step - 1) / 3) * 170 },
        data: {
          agentId,
          label: agent.name,
          role: agent.role,
          model: agent.model,
          step,
          inputTransform: "",
        },
      },
    ]);
  }

  async function save() {
    if (!title.trim() || errors.length) return;
    const payload: WorkflowInput & { id?: string } = {
      ...(editing ? { id: editing.id } : {}),
      title: title.trim(),
      execution_type: executionType,
      steps: nodes.map((node) => ({
        step_number: node.data.step,
        agent_id: node.data.agentId,
        depends_on: edges
          .filter((edge) => edge.target === node.id)
          .map((edge) => Number(edge.source))
          .sort((a, b) => a - b),
        input_transform: node.data.inputTransform,
      })),
      graph_layout: Object.fromEntries(nodes.map((node) => [node.id, node.position])),
    };
    try {
      await saveMutation.mutateAsync(payload);
      setEditorOpen(false);
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "Could not save workflow.");
    }
  }

  return (
    <AppShell>
      <section className="min-w-0">
        <header className="flex min-h-20 flex-wrap items-center justify-between gap-3 border-b border-border px-6 py-4 lg:px-8">
          <div>
            <h1 className="text-xl font-semibold tracking-tight">Workflows</h1>
            <p className="mt-1 text-xs text-muted-foreground">
              Orchestration design · Compose agents into sequential, parallel, or hybrid execution
              graphs.
            </p>
          </div>
          <Button onClick={() => openEditor()} disabled={!agents.length}>
            <Plus size={16} /> New workflow
          </Button>
        </header>
        <div className="mx-auto max-w-360 p-6 lg:p-10">
          {workflowsQuery.isLoading && (
            <div className="grid min-h-52 place-items-center">
              <LoaderCircle className="animate-spin text-muted-foreground" />
            </div>
          )}
          {workflowsQuery.isError && (
            <div
              role="alert"
              className="rounded-xl border border-destructive/60 p-5 text-sm text-destructive"
            >
              Could not load workflows.{" "}
              <button onClick={() => void workflowsQuery.refetch()} className="underline">
                Try again
              </button>
            </div>
          )}
          {agentsQuery.isSuccess && agents.length === 0 && (
            <p className="mb-4 rounded-lg border border-border p-4 text-sm text-muted-foreground">
              Create an agent before building a workflow.
            </p>
          )}
          {!workflowsQuery.isLoading &&
            workflowsQuery.isSuccess &&
            workflowsQuery.data.items.length === 0 && (
              <div className="grid min-h-64 place-items-center rounded-xl border border-dashed border-border bg-card p-8 text-center">
                <div>
                  <GitBranch className="mx-auto text-status-completed" />
                  <h2 className="mt-4 font-semibold">No workflows yet</h2>
                  <p className="mt-2 text-sm text-muted-foreground">
                    Create a workflow to define how your agents collaborate.
                  </p>
                </div>
              </div>
            )}
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            {(workflowsQuery.data?.items ?? []).map((workflow) => (
              <article key={workflow.id} className="rounded-xl border border-border bg-card p-5">
                <span className="w-full text-left flex flex-col">
                  <p className="font-semibold">{workflow.title}</p>
                  <p className="mt-2 text-xs uppercase tracking-wider text-status-completed">
                    {workflow.execution_type}
                  </p>
                  <p className="mt-3 text-sm text-muted-foreground">
                    {workflow.steps.length} steps · updated{" "}
                    {new Date(workflow.updated_at).toLocaleDateString()}
                  </p>
                </span>
                <footer className="mt-4 flex justify-end gap-2 border-t border-border pt-3">
                  <Button
                    aria-label={`Edit ${workflow.title}`}
                    onClick={() => openEditor(workflow)}
                    size="icon"
                  >
                    <Pencil size={18} />
                  </Button>
                  <Button
                    aria-label={`Delete ${workflow.title}`}
                    variant="destructive"
                    size="icon"
                    disabled={deleteMutation.isPending}
                    onClick={() => {
                      deleteMutation.reset();
                      setDeleting(workflow);
                    }}
                  >
                    <Trash2 size={18} />
                  </Button>
                </footer>
              </article>
            ))}
          </div>
        </div>
      </section>
      {deleting && (
        <DeleteConfirmationDialog
          key={deleting.id}
          name={deleting.title}
          entity="workflow"
          pending={deleteMutation.isPending}
          onClose={() => setDeleting(null)}
          onConfirm={async () => {
            await deleteMutation.mutateAsync(deleting.id);
          }}
        />
      )}
      <Dialog
        open={editorOpen}
        onOpenChange={(open) => {
          if (!saveMutation.isPending) setEditorOpen(open);
        }}
      >
        <DialogContent
          showCloseButton={false}
          className="flex h-[92vh] flex-col gap-0 overflow-hidden p-0 sm:max-w-7xl"
        >
          <DialogTitle className="sr-only">Workflow editor</DialogTitle>
          <header className="flex flex-wrap items-center gap-3 border-b border-border p-4">
            <Input
              id="workflow-title"
              value={title}
              onChange={(event) => setTitle(event.target.value)}
              placeholder="Workflow title"
              className="min-w-40 flex-1 rounded-md border border-border bg-background px-3 py-2 text-sm"
            />
            <span className="rounded-md bg-status-completed/10 px-3 py-2 text-xs font-medium uppercase text-status-completed">
              {executionType}
            </span>
            <Button size="sm" variant="secondary" disabled={!canUndo} onClick={undoGraph}>
              Undo
            </Button>
            <Button size="sm" variant="secondary" disabled={!canRedo} onClick={redoGraph}>
              Redo
            </Button>
            <Button size="sm" variant="secondary" onClick={autoLayout}>
              Auto layout
            </Button>
            <Button
              disabled={saveMutation.isPending}
              onClick={() => setEditorOpen(false)}
              aria-label="Close editor"
              size="icon"
              variant="ghost"
            >
              <X size={18} />
            </Button>
          </header>
          <div className="flex min-h-0 flex-1">
            <aside className="w-56 shrink-0 overflow-y-auto border-r border-border p-3">
              <p className="mb-3 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                Agent palette
              </p>
              {agents.map((agent) => (
                <Button
                  key={agent.id}
                  variant="ghost"
                  disabled={agent.available === false}
                  title={
                    agent.available === false
                      ? "Reconfigure this agent with an enabled model first."
                      : undefined
                  }
                  onClick={() => addAgent(agent.id)}
                  className="mb-2 w-full rounded-lg border border-border p-3 text-left hover:border-status-completed/50"
                >
                  <span className="block truncate text-xs font-medium">{agent.name}</span>
                  <span className="mt-1 block truncate font-mono text-[10px] text-muted-foreground">
                    {agent.model}
                  </span>
                </Button>
              ))}
              <div className="mt-4 border-t border-border pt-3">
                <label htmlFor="preset" className="text-xs text-muted-foreground">
                  Arrange preset
                </label>
                <Select
                  value={preset}
                  onValueChange={(value) => {
                    if (!value) return;
                    const kind = value as WorkflowType;
                    setPreset(kind);
                    rememberGraph();
                    setEdges([]);
                    setNodes((current) =>
                      current.map((node, index) => ({
                        ...node,
                        position: {
                          x: 100 + (kind === "sequential" ? 0 : (index % 3) * 240),
                          y: 70 + index * (kind === "sequential" ? 130 : 180),
                        },
                      })),
                    );
                    if (kind === "sequential")
                      setEdges(
                        nodes.slice(1).map((node, index) => ({
                          id: `${nodes[index].id}-${node.id}`,
                          source: nodes[index].id,
                          target: node.id,
                        })),
                      );
                    else if (kind === "parallel" && nodes.length > 1) {
                      const final = nodes[nodes.length - 1];
                      setEdges(
                        nodes.slice(0, -1).map((node) => ({
                          id: `${node.id}-${final.id}`,
                          source: node.id,
                          target: final.id,
                        })),
                      );
                    }
                  }}
                >
                  <SelectTrigger
                    id="preset"
                    aria-label="Arrange preset"
                    className="mt-2 w-full rounded-md border border-border bg-background px-2 py-2 text-xs"
                  >
                    {preset === "sequential"
                      ? "Sequential chain"
                      : preset === "parallel"
                        ? "Parallel + aggregator"
                        : "Hybrid graph"}
                  </SelectTrigger>
                  <SelectContent>
                    <SelectGroup>
                      <SelectItem value="hybrid">Hybrid graph</SelectItem>
                      <SelectItem value="sequential">Sequential chain</SelectItem>
                      <SelectItem value="parallel">Parallel + aggregator</SelectItem>
                    </SelectGroup>
                  </SelectContent>
                </Select>
              </div>
            </aside>
            <div className="workflow-canvas min-w-0 flex-1 bg-background">
              <ReactFlow
                nodes={nodes}
                edges={edges}
                onNodesChange={(changes) => {
                  if (changes.some((change) => change.type === "remove")) rememberGraph();
                  onNodesChange(changes);
                }}
                onNodeDragStart={rememberGraph}
                onEdgesChange={(changes) => {
                  if (changes.some((change) => change.type === "remove")) rememberGraph();
                  onEdgesChange(changes);
                }}
                onConnect={onConnect}
                onNodeClick={(_, node) => setSelectedId(node.id)}
                fitView
              >
                <Background color="var(--border)" />
                <Controls />
                <MiniMap pannable zoomable style={{ width: 140, height: 100 }} />
              </ReactFlow>
            </div>
            <aside className="w-64 shrink-0 overflow-y-auto border-l border-border p-4">
              <p className="mb-4 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                Node properties
              </p>
              {selected ? (
                <>
                  <p className="truncate text-sm font-medium">{selected.data.label}</p>
                  <p className="mt-1 text-xs text-muted-foreground">
                    Step {selected.data.step} · {selected.data.model}
                  </p>
                  <label
                    htmlFor="input-transform"
                    className="mt-5 block text-xs text-muted-foreground"
                  >
                    Input transform
                  </label>
                  <Textarea
                    id="input-transform"
                    key={`${editing?.id ?? "new"}-${selected.id}`}
                    value={selected.data.inputTransform}
                    onChange={(event) =>
                      setNodes((current) =>
                        current.map((node) =>
                          node.id === selected.id
                            ? {
                                ...node,
                                data: { ...node.data, inputTransform: event.target.value },
                              }
                            : node,
                        ),
                      )
                    }
                    onFocus={rememberGraph}
                    rows={8}
                    className="mt-2 w-full resize-y rounded-md border border-border bg-background p-2 font-mono text-xs"
                  />
                  <p className="mt-2 text-[10px] text-muted-foreground">
                    Leave empty to include the subtask, context and dependency outputs
                    automatically. Available variables: task, subtask, context, steps.N.output.
                  </p>
                  <Button
                    variant="ghost"
                    onClick={() => {
                      rememberGraph();
                      setNodes((current) => current.filter((node) => node.id !== selected.id));
                      setEdges((current) =>
                        current.filter(
                          (edge) => edge.source !== selected.id && edge.target !== selected.id,
                        ),
                      );
                      setSelectedId(null);
                    }}
                    className="mt-5 flex items-center gap-2 text-xs text-destructive"
                  >
                    <Trash2 size={13} /> Remove node
                  </Button>
                </>
              ) : (
                <p className="text-xs text-muted-foreground">
                  Select a graph node to edit its input template.
                </p>
              )}
              <div className="mt-6 border-t border-border pt-4">
                <p className="text-xs font-semibold text-muted-foreground">Validation</p>
                {errors.length ? (
                  <ul className="mt-2 list-inside list-disc space-y-1 text-xs text-destructive">
                    {errors.map((error) => (
                      <li key={error}>{error}</li>
                    ))}
                  </ul>
                ) : (
                  <p className="mt-2 text-xs text-status-completed">Graph is valid.</p>
                )}
              </div>
            </aside>
          </div>
          {notice && (
            <p
              role="alert"
              className="border-t border-destructive/60 px-4 py-2 text-sm text-destructive"
            >
              {notice}
            </p>
          )}
          <footer className="flex justify-end gap-2 border-t border-border p-3">
            <Button
              variant="secondary"
              onClick={() => setEditorOpen(false)}
              className="rounded-md border border-border px-4 py-2 text-sm text-foreground"
            >
              Cancel
            </Button>
            <Button
              variant="default"
              onClick={() => void save()}
              disabled={!title.trim() || errors.length > 0 || saveMutation.isPending}
            >
              {saveMutation.isPending ? (
                <LoaderCircle size={15} className="animate-spin" />
              ) : (
                <Save size={15} />
              )}{" "}
              Save workflow
            </Button>
          </footer>
        </DialogContent>
      </Dialog>
    </AppShell>
  );
}
