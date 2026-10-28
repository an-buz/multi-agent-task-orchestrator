import type { RunEvent, RunStep } from "@/features/runs/types";

export function consoleEvents(events: RunEvent[]): RunEvent[] {
  return events.filter(
    (event) =>
      event.event !== "agent:stream_chunk" || (event.data ?? event.payload)?.reset === true,
  );
}

export function eventPresentation(event: RunEvent, steps: RunStep[]) {
  const data = event.data ?? event.payload ?? {};
  const agent = steps.find((step) => step.step_number === data.stepNumber)?.agent_name;
  const tool = event.event.includes("tool");
  const toolName = typeof data.toolName === "string" ? data.toolName : "Tool";
  const tone = tool
    ? "cyan"
    : event.event.startsWith("agent:") && !event.event.endsWith("completed")
      ? "violet"
      : "emerald";
  const tag = tool
    ? `Tool: ${toolName}`
    : tone === "violet"
      ? `Agent: ${agent ?? "Update"}`
      : `Status: ${event.event.split(":").at(-1)?.replaceAll("_", " ")}`;
  let message: string;
  if (typeof data.summary === "string") message = data.summary;
  else if (event.event === "run:snapshot") message = "Persisted run state restored.";
  else if (event.event === "plan:ready")
    message = "Execution plan prepared and awaiting confirmation.";
  else if (event.event === "task:started") message = "Workflow execution started.";
  else if (event.event === "task:paused") {
    const reasons = Array.isArray(data.pauseReasons) ? data.pauseReasons : [];
    const explanations = [
      ...(reasons.includes("MODEL_UNAVAILABLE")
        ? [
            "An agent model is unavailable. Check Models and agent configuration; restart the worker if provider credentials changed.",
          ]
        : []),
      ...(reasons.includes("USER_DECISION_REQUIRED")
        ? ["Your decision is required. Review the agent findings."]
        : []),
    ];
    message = `Workflow paused. ${explanations.join(" ") || "Check run details for the required action."}`;
  } else if (event.event === "decision:required")
    message = "Agent findings require your decision. New steps are blocked.";
  else if (event.event === "decision:resolved") message = "User decision saved.";
  else if (event.event === "task:resumed") message = "Workflow execution resumed.";
  else if (event.event === "task:cancelled") message = "Workflow execution cancelled.";
  else if (event.event === "task:failed")
    message = "Workflow execution failed. Review failed steps.";
  else if (event.event === "task:finished")
    message = `Workflow completed${typeof data.totalTokens === "number" ? ` · ${data.totalTokens.toLocaleString()} tokens` : ""}.`;
  else if (event.event === "agent:stream_chunk" && data.reset === true)
    message = `${agent ?? "Agent"}: waiting for the model response.`;
  else if (event.event === "agent:status_change" && typeof data.status === "string")
    message =
      data.status === "IN_PROGRESS"
        ? `${agent ?? "Agent"}: preparing the model request.`
        : `${agent ?? "Agent"}: ${data.status.toLowerCase().replaceAll("_", " ")}.`;
  else if (event.event === "agent:completed") message = `${agent ?? "Agent"} completed the step.`;
  else if (event.event === "agent:failed") {
    const error = data.error;
    const reason =
      error && typeof error === "object" && "message" in error && typeof error.message === "string"
        ? error.message
        : "Review the step details.";
    message = `${agent ?? "Agent"} failed. ${reason}`;
  } else if (event.event === "agent:tool_call")
    message = `${agent ?? "Agent"} is calling ${toolName}.`;
  else if (event.event === "agent:tool_result")
    message = `${toolName} ${data.ok === false ? "failed" : "completed"}.`;
  else message = "Run activity updated.";
  return {
    tag: tag.replace(/\s+/gu, " ").trim(),
    tone,
    message: message.replace(/\s+/gu, " ").trim(),
  };
}
