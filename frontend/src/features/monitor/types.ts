export interface RunEvent<TPayload = Record<string, unknown>> {
  event: string;
  runId: string;
  timestamp: string;
  payload: TPayload;
}
