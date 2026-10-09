import { apiRequest } from "@/lib/api";
import type { CreateRunInput, CreatedRun, RunDetails, RunEvent, RunListResponse } from "./types";

export const runsQueryKey = ["runs"] as const;

export function listRuns(): Promise<RunListResponse> {
  return apiRequest<RunListResponse>("/runs");
}

export function getRun(id: string): Promise<RunDetails> {
  return apiRequest<RunDetails>(`/runs/${id}`);
}

export function deleteRun(id: string): Promise<void> {
  return apiRequest<void>(`/runs/${id}`, { method: "DELETE" });
}

export function createRun(input: CreateRunInput): Promise<RunDetails | CreatedRun> {
  return apiRequest<RunDetails | CreatedRun>("/runs", {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export function waitForRunPlan(id: string): Promise<RunDetails> {
  return new Promise((resolve, reject) => {
    let settled = false;
    const timer = window.setTimeout(
      () => finish(new Error("Timed out waiting for the execution plan.")),
      60_000,
    );
    const close = subscribeToRun(
      id,
      (event) => {
        if (["run:snapshot", "plan:ready", "task:failed", "task:cancelled"].includes(event.event)) {
          checkPlan();
        }
      },
      () => undefined,
    );
    function checkPlan() {
      void getRun(id).then(
        (run) => {
          if (run.status === "AWAITING_CONFIRMATION" && run.plan) finish(undefined, run);
          else if (run.status === "FAILED") {
            finish(
              new Error(run.planning_error?.message ?? "Could not generate the execution plan."),
            );
          } else if (run.status === "CANCELLED") finish(new Error("Planning was cancelled."));
        },
        (error: unknown) => finish(error),
      );
    }
    // A fast worker may finish before EventSource connects; snapshot/GET closes that race.
    checkPlan();
    function finish(error?: unknown, run?: RunDetails) {
      if (settled) return;
      settled = true;
      window.clearTimeout(timer);
      close();
      if (error) reject(error);
      else if (run) resolve(run);
      else reject(new Error("The server did not return the execution plan."));
    }
  });
}

export function confirmRun(id: string): Promise<RunDetails> {
  return apiRequest<RunDetails>(`/runs/${id}/confirm`, { method: "POST" });
}

export function editRunPlan(
  id: string,
  plan: NonNullable<RunDetails["plan"]>,
): Promise<RunDetails> {
  return apiRequest<RunDetails>(`/runs/${id}/plan`, {
    method: "PATCH",
    body: JSON.stringify({ steps: plan }),
  });
}

export function cancelRun(id: string): Promise<RunDetails> {
  return apiRequest<RunDetails>(`/runs/${id}/cancel`, { method: "POST" });
}

export function retryRunStep(id: string, step: number): Promise<RunDetails> {
  return apiRequest<RunDetails>(`/runs/${id}/steps/${step}/retry`, { method: "POST" });
}

export function exportRun(id: string, format: "json" | "md" | "pdf"): Promise<Response> {
  const base = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1";
  return fetch(`${base}/runs/${id}/export?format=${format}`);
}

export function subscribeToRun(
  id: string,
  onEvent: (event: RunEvent) => void,
  onError: () => void,
  options?: { after?: number },
) {
  const base = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1";
  const replay = options?.after !== undefined ? `?after=${options.after}` : "";
  const source = new EventSource(`${base}/runs/${id}/events${replay}`);
  const eventNames = [
    "run:snapshot",
    "plan:ready",
    "task:started",
    "agent:status_change",
    "agent:stream_chunk",
    "agent:tool_call",
    "agent:tool_result",
    "agent:retry",
    "agent:completed",
    "agent:failed",
    "task:finished",
    "task:failed",
    "task:cancelled",
  ];
  const listeners = eventNames.map((name) => {
    const listener: EventListener = (message) => {
      try {
        const incoming = message as MessageEvent<string>;
        const event = JSON.parse(incoming.data) as RunEvent;
        onEvent({ ...event, id: incoming.lastEventId || undefined });
      } catch {
        /* Ignore malformed mock events. */
      }
    };
    source.addEventListener(name, listener);
    return [name, listener] as const;
  });
  source.onerror = onError;
  return () => {
    listeners.forEach(([name, listener]) => source.removeEventListener(name, listener));
    source.close();
  };
}
