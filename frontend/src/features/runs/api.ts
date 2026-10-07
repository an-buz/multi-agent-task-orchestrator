import { apiRequest } from "@/lib/api";
import type { CreateRunInput, CreatedRun, RunDetails, RunEvent, RunListResponse } from "./types";

export const runsQueryKey = ["runs"] as const;

export function listRuns(): Promise<RunListResponse> {
  return apiRequest<RunListResponse>("/runs");
}

export function getRun(id: string): Promise<RunDetails> {
  return apiRequest<RunDetails>(`/runs/${id}`);
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
        if (event.event !== "plan:ready") return;
        void getRun(id).then(
          (run) => finish(undefined, run),
          (error: unknown) => finish(error),
        );
      },
      () => undefined,
    );
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
) {
  const base = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1";
  const source = new EventSource(`${base}/runs/${id}/events`);
  const eventNames = [
    "run:snapshot",
    "plan:ready",
    "task:started",
    "agent:status_change",
    "agent:stream_chunk",
    "agent:tool_call",
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
        onEvent(JSON.parse((message as MessageEvent<string>).data) as RunEvent);
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
