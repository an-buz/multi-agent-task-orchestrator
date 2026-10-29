import { apiRequest } from "@/lib/api";

export interface Collection<T> {
  items: T[];
  total: number;
}

// Selectors and client-side search require every page of the catalogue.
export async function loadCatalogue<T>(path: string, signal?: AbortSignal): Promise<Collection<T>> {
  const items: T[] = [];
  let total = 0;

  do {
    const page = await apiRequest<Collection<T>>(`${path}?limit=50&offset=${items.length}`, {
      signal,
    });

    total = page.total;

    if (!page.items.length && items.length < total) {
      throw new Error("The catalogue changed while loading. Please try again.");
    }

    items.push(...page.items);
  } while (items.length < total);

  return { items, total };
}
