export interface Collection<T> {
  items: T[];
  total: number;
}

export function upsertItem<T extends { id: string }>(
  current: Collection<T> | undefined,
  item: T,
): Collection<T> | undefined {
  if (!current) return current;
  const exists = current.items.some((entry) => entry.id === item.id);
  return {
    ...current,
    items: exists
      ? current.items.map((entry) => (entry.id === item.id ? item : entry))
      : [item, ...current.items],
    total: current.total + Number(!exists),
  };
}

export function removeItem<T extends { id: string }>(
  current: Collection<T> | undefined,
  id: string,
): Collection<T> | undefined {
  if (!current) return current;
  return {
    ...current,
    items: current.items.filter((item) => item.id !== id),
    total: Math.max(0, current.total - Number(current.items.some((item) => item.id === id))),
  };
}
