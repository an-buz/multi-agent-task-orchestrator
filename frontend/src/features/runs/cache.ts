import type { QueryClient } from "@tanstack/react-query";
import type { RunDetails } from "./types";

export const runsQueryKey = ["runs"] as const;
export const runQueryKey = (id: string | undefined) => [...runsQueryKey, id] as const;
export const runEventsQueryKey = (id: string | undefined) =>
  [...runQueryKey(id), "events"] as const;

export async function cacheRun(client: QueryClient, run: RunDetails): Promise<void> {
  await client.cancelQueries({ queryKey: runQueryKey(run.id), exact: true });
  client.setQueryData(runQueryKey(run.id), run);
}
