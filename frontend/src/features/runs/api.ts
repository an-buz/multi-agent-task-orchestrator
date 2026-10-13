import { apiRequest, apiResponse, apiUrl } from "@/lib/api";
import type { CreateRunInput, CreatedRun, RunDetails, RunEvent, RunListResponse } from "./types";

export function listRuns(signal?: AbortSignal): Promise<RunListResponse> {
  return apiRequest<RunListResponse>("/runs", { signal });
}

export function getRun(id: string, signal?: AbortSignal): Promise<RunDetails> {
  return apiRequest<RunDetails>(`/runs/${id}`, { signal });
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

export function waitForRunPlan(id: string, signal?: AbortSignal): Promise<RunDetails> {
  return new Promise((resolve, reject) => {
    if (signal?.aborted) {
      reject(signal.reason);
      return;
    }
    let settled = false;
    let checking = false;
    const controller = new AbortController();
    const onAbort = () =>
      finish(signal?.reason ?? new DOMException("Planning wait cancelled.", "AbortError"));
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
    // Polling is a fallback when SSE cannot connect or an event is lost.
    const poll = window.setInterval(checkPlan, 2000);
    signal?.addEventListener("abort", onAbort, { once: true });
    function checkPlan() {
      if (settled || checking) return;
      checking = true;
      void getRun(id, controller.signal)
        .then(
          (run) => {
            if (run.status === "AWAITING_CONFIRMATION" && run.plan) finish(undefined, run);
            else if (run.status === "FAILED") {
              finish(
                new Error(run.planning_error?.message ?? "Could not generate the execution plan."),
              );
            } else if (run.status === "CANCELLED") finish(new Error("Planning was cancelled."));
          },
          (error: unknown) => finish(error),
        )
        .finally(() => {
          checking = false;
        });
    }
    // A fast worker may finish before EventSource connects; snapshot/GET closes that race.
    checkPlan();
    function finish(error?: unknown, run?: RunDetails) {
      if (settled) return;
      settled = true;
      window.clearTimeout(timer);
      window.clearInterval(poll);
      signal?.removeEventListener("abort", onAbort);
      controller.abort();
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
  return apiResponse(`/runs/${id}/export?format=${format}`);
}

export function subscribeToRun(
  id: string,
  onEvent: (event: RunEvent) => void,
  onError: () => void,
  options?: { after?: number },
) {
  const replay = options?.after !== undefined ? `?after=${options.after}` : "";
  const source = new EventSource(apiUrl(`/runs/${id}/events${replay}`));
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
      const incoming = message as MessageEvent<string>;
      let parsed: unknown;
      try {
        parsed = JSON.parse(incoming.data);
      } catch {
        return;
      }
      if (!parsed || typeof parsed !== "object" || !("event" in parsed) || parsed.event !== name)
        return;
      const event = parsed as RunEvent;
      onEvent({ ...event, id: incoming.lastEventId || undefined });
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
