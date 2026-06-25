import { useEffect, useMemo, useRef, useState } from 'react';
import { useStore } from '../../store/AppStore';
import type { Version } from '../../types';
import { buildForest, flattenForest, type TreeNode } from '../../lib/tree';
import { classNames, formatRelativeTime } from '../../lib/format';
import { Card, CardHeader } from '../ui/Card';
import { TagBadge } from '../ui/Badge';
import { IconTree } from '../ui/icons';

const DOT_BY_TAG: Record<string, string> = {
  golden: 'bg-accent',
  good: 'bg-success',
  bad: 'bg-danger',
  experimental: 'bg-brand',
  baseline: 'bg-muted',
};

function nodeDot(version: Version): string {
  const primary = version.tags[0];
  return (primary ? DOT_BY_TAG[primary] : undefined) ?? 'bg-border';
}

export function VersionTree() {
  const { versions, selectedId, select, headId } = useStore();
  const forest = useMemo(() => buildForest(versions), [versions]);
  const flat = useMemo(() => flattenForest(forest), [forest]);
  const order = useMemo(() => flat.map((n) => n.version.id), [flat]);

  const refs = useRef<Record<string, HTMLButtonElement | null>>({});
  const [focusId, setFocusId] = useState(selectedId);

  useEffect(() => setFocusId(selectedId), [selectedId]);

  const focusNode = (id: string | undefined) => {
    if (!id) return;
    setFocusId(id);
    refs.current[id]?.focus();
  };

  const onKeyDown = (e: React.KeyboardEvent, id: string) => {
    const idx = order.indexOf(id);
    switch (e.key) {
      case 'ArrowDown':
        e.preventDefault();
        focusNode(order[Math.min(order.length - 1, idx + 1)]);
        break;
      case 'ArrowUp':
        e.preventDefault();
        focusNode(order[Math.max(0, idx - 1)]);
        break;
      case 'Home':
        e.preventDefault();
        focusNode(order[0]);
        break;
      case 'End':
        e.preventDefault();
        focusNode(order[order.length - 1]);
        break;
      case 'Enter':
      case ' ':
        e.preventDefault();
        select(id);
        break;
      default:
        break;
    }
  };

  const renderNode = (node: TreeNode) => {
    const v = node.version;
    const selected = v.id === selectedId;
    const isHead = v.id === headId;
    return (
      <li key={v.id} role="treeitem" aria-selected={selected} aria-expanded={node.children.length > 0 || undefined}>
        <button
          ref={(el) => (refs.current[v.id] = el)}
          type="button"
          tabIndex={focusId === v.id ? 0 : -1}
          onClick={() => select(v.id)}
          onKeyDown={(e) => onKeyDown(e, v.id)}
          className={classNames(
            'focus-ring group flex w-full items-center gap-2.5 rounded-xl px-2.5 py-2 text-left transition-all duration-200',
            selected
              ? 'bg-brand/8 text-ink ring-1 ring-brand/30'
              : 'text-ink-soft hover:bg-surface-2',
          )}
        >
          <span className={classNames('h-2.5 w-2.5 shrink-0 rounded-full', nodeDot(v))} />
          <span
            className={classNames(
              'font-mono text-xs font-semibold',
              selected ? 'text-brand' : 'text-ink',
            )}
          >
            {v.id}
          </span>
          <span className="min-w-0 flex-1 truncate text-sm">{v.summary}</span>
          {isHead && (
            <span className="hidden rounded-md bg-brand/12 px-1.5 py-0.5 font-mono text-[10px] font-semibold text-brand sm:inline">
              HEAD
            </span>
          )}
          {v.tags[0] && (
            <span className="hidden md:inline">
              <TagBadge tag={v.tags[0]} />
            </span>
          )}
          <span className="hidden shrink-0 text-2xs text-muted lg:inline">
            {formatRelativeTime(v.createdAt)}
          </span>
        </button>
        {node.children.length > 0 && (
          <ul role="group" className="ml-[1.1rem] mt-1 space-y-1 border-l border-border pl-3">
            {node.children.map(renderNode)}
          </ul>
        )}
      </li>
    );
  };

  return (
    <Card className="p-5">
      <CardHeader
        kicker="Lineage"
        title="Version Tree"
        icon={<IconTree className="h-5 w-5" />}
        actions={
          <span className="rounded-lg bg-surface-2 px-2 py-1 text-2xs font-semibold text-muted">
            {versions.length} nodes
          </span>
        }
      />
      <p className="mt-1 text-2xs text-muted">
        Each branch is a <span className="font-mono">--from</span> fork. Select a node to inspect it.
      </p>
      <ul role="tree" aria-label="Version tree" className="mt-4 space-y-1">
        {forest.map(renderNode)}
      </ul>
    </Card>
  );
}
