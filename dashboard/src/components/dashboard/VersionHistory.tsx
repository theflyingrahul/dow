import { useMemo } from 'react';
import { useStore } from '../../store/AppStore';
import type { VerdictLevel } from '../../types';
import { compareVersions } from '../../lib/drift';
import { classNames, formatRelativeTime } from '../../lib/format';
import { Card, CardHeader } from '../ui/Card';
import { Badge, TagBadge, VERDICT_TONE } from '../ui/Badge';
import { IconClock } from '../ui/icons';

// Static map (avoids dynamically constructed Tailwind class names).
const VERDICT_DOT: Record<VerdictLevel, string> = {
  pass: 'bg-success',
  warn: 'bg-warning',
  fail: 'bg-danger',
};

export function VersionHistory() {
  const { versions, versionsById, selectedId, select, typicalDrift } = useStore();

  const ordered = useMemo(
    () =>
      [...versions].sort(
        (a, b) => new Date(b.createdAt).getTime() - new Date(a.createdAt).getTime(),
      ),
    [versions],
  );

  return (
    <Card className="flex h-full flex-col p-5">
      <CardHeader
        kicker="Activity"
        title="Version History"
        icon={<IconClock className="h-5 w-5" />}
      />

      <ol className="scroll-slim mt-5 max-h-[26rem] flex-1 overflow-y-auto pr-1">
        {ordered.map((v, i) => {
          const parent = v.parentId ? versionsById[v.parentId] : null;
          const cmp = parent ? compareVersions(parent, v, { typicalDrift }) : null;
          const selected = v.id === selectedId;
          const isLast = i === ordered.length - 1;

          return (
            <li key={v.id} className="flex gap-3">
              {/* Timeline rail */}
              <div className="flex w-4 flex-col items-center" aria-hidden="true">
                <span
                  className={classNames(
                    'mt-3 h-2.5 w-2.5 shrink-0 rounded-full ring-4 ring-surface transition-colors',
                    selected ? 'bg-brand' : cmp ? VERDICT_DOT[cmp.verdict] : 'bg-muted',
                  )}
                />
                {!isLast && <span className="w-px flex-1 bg-border" />}
              </div>

              <button
                type="button"
                onClick={() => select(v.id)}
                aria-current={selected ? 'true' : undefined}
                className={classNames(
                  'focus-ring mb-1 flex-1 rounded-xl px-3 py-2.5 text-left transition-all duration-200',
                  selected ? 'bg-brand/8 ring-1 ring-brand/25' : 'hover:bg-surface-2',
                )}
              >
                <div className="flex items-center justify-between gap-2">
                  <div className="flex items-center gap-2">
                    <span className="font-mono text-xs font-semibold text-ink">{v.id}</span>
                    {cmp ? (
                      <Badge tone={VERDICT_TONE[cmp.verdict]}>{cmp.verdictLabel}</Badge>
                    ) : (
                      <Badge tone="neutral">baseline</Badge>
                    )}
                  </div>
                  <time className="shrink-0 text-2xs text-muted" dateTime={v.createdAt}>
                    {formatRelativeTime(v.createdAt)}
                  </time>
                </div>

                <p className="mt-1 text-sm leading-snug text-ink-soft">{v.summary}</p>

                <div className="mt-2 flex flex-wrap items-center gap-2 text-2xs text-muted">
                  {v.changedField && (
                    <span className="inline-flex items-center gap-1 rounded-md bg-surface-2 px-1.5 py-0.5 font-mono text-[10px] text-ink-soft">
                      {v.changedField}
                    </span>
                  )}
                  <span>by {v.author}</span>
                  {v.tags.map((t) => (
                    <TagBadge key={t} tag={t} />
                  ))}
                </div>
              </button>
            </li>
          );
        })}
      </ol>
    </Card>
  );
}
