import type { MetricKey, Version } from '../types';

export interface TreeNode {
  version: Version;
  children: TreeNode[];
  depth: number;
}

/** Build a forest of version nodes from parent-child links, sorted by date. */
export function buildForest(versions: Version[]): TreeNode[] {
  const byId = new Map(versions.map((v) => [v.id, v]));
  const childrenOf = new Map<string | null, Version[]>();

  for (const v of versions) {
    const key = v.parentId && byId.has(v.parentId) ? v.parentId : null;
    const list = childrenOf.get(key) ?? [];
    list.push(v);
    childrenOf.set(key, list);
  }

  const sortByDate = (a: Version, b: Version) =>
    new Date(a.createdAt).getTime() - new Date(b.createdAt).getTime();

  const build = (version: Version, depth: number): TreeNode => ({
    version,
    depth,
    children: (childrenOf.get(version.id) ?? []).sort(sortByDate).map((c) => build(c, depth + 1)),
  });

  return (childrenOf.get(null) ?? []).sort(sortByDate).map((root) => build(root, 0));
}

/** Flatten a forest depth-first (used for keyboard navigation order). */
export function flattenForest(forest: TreeNode[]): TreeNode[] {
  const out: TreeNode[] = [];
  const walk = (node: TreeNode) => {
    out.push(node);
    node.children.forEach(walk);
  };
  forest.forEach(walk);
  return out;
}

/** Root → node lineage for a version (inclusive). */
export function getLineage(versionsById: Record<string, Version>, id: string): Version[] {
  const chain: Version[] = [];
  let current: Version | undefined = versionsById[id];
  const guard = new Set<string>();
  while (current && !guard.has(current.id)) {
    guard.add(current.id);
    chain.unshift(current);
    current = current.parentId ? versionsById[current.parentId] : undefined;
  }
  return chain;
}

/** Series of a single metric along a version's lineage (for sparklines). */
export function lineageMetricSeries(
  versionsById: Record<string, Version>,
  id: string,
  key: MetricKey,
): number[] {
  return getLineage(versionsById, id)
    .map((v) => v.metrics[key] as number | undefined)
    .filter((x): x is number => x !== undefined);
}
