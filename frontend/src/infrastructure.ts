export type Group = {
  id: number;
  name: string;
  parent_id: number | null;
  revision: number;
};
export type Tag = { id: number; name: string; revision: number };
export type Resource = {
  id: number;
  name: string;
  description: string;
  address: string;
  kind: string;
  operating_system: string;
  environment: string;
  group_id: number | null;
  tag_ids: number[];
  revision: number;
  state: string;
  monitor_count: number;
  paused_count: number;
};
export function groupLabel(id: number, groups: Group[]): string {
  const parts: string[] = [];
  const seen = new Set<number>();
  let current = groups.find((g) => g.id === id);
  while (current && !seen.has(current.id)) {
    parts.unshift(current.name);
    seen.add(current.id);
    current = groups.find((g) => g.id === current!.parent_id);
  }
  return parts.join(" / ");
}
export function isDescendant(
  id: number,
  parent: number,
  groups: Group[],
): boolean {
  const seen = new Set<number>();
  let current = groups.find((g) => g.id === id);
  while (current && !seen.has(current.id)) {
    if (current.id === parent) return true;
    seen.add(current.id);
    current = groups.find((g) => g.id === current!.parent_id);
  }
  return false;
}
