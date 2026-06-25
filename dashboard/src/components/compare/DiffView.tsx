import { useMemo, useState } from 'react';
import type { Version } from '../../types';
import { diffLines, diffStats, serializeSpec, toSideBySide } from '../../lib/diff';
import { classNames } from '../../lib/format';
import { Card, CardHeader } from '../ui/Card';
import { SegmentedControl } from '../ui/SegmentedControl';
import { IconCompare } from '../ui/icons';

type Mode = 'split' | 'inline';
type Target = 'spec' | 'outputs';

function linesFor(version: Version, target: Target): string[] {
  return target === 'spec' ? serializeSpec(version.config) : version.outputs.map((o) => o.output);
}

export function DiffView({ from, to }: { from: Version; to: Version }) {
  const [mode, setMode] = useState<Mode>('split');
  const [target, setTarget] = useState<Target>('spec');

  const ops = useMemo(
    () => diffLines(linesFor(from, target), linesFor(to, target)),
    [from, to, target],
  );
  const stats = useMemo(() => diffStats(ops), [ops]);
  const rows = useMemo(() => toSideBySide(ops), [ops]);

  return (
    <Card className="p-5">
      <CardHeader
        kicker="Difference"
        title="Diff View"
        icon={<IconCompare className="h-5 w-5" />}
        actions={
          <div className="hidden items-center gap-2 sm:flex">
            <span className="metric-num text-2xs font-semibold text-success-ink">+{stats.added}</span>
            <span className="metric-num text-2xs font-semibold text-danger-ink">−{stats.removed}</span>
          </div>
        }
      />

      <div className="mt-4 flex flex-wrap items-center justify-between gap-3">
        <SegmentedControl
          ariaLabel="Diff content"
          size="sm"
          value={target}
          onChange={(v) => setTarget(v as Target)}
          options={[
            { value: 'spec', label: 'Spec' },
            { value: 'outputs', label: 'Outputs' },
          ]}
        />
        <SegmentedControl
          ariaLabel="Diff layout"
          size="sm"
          value={mode}
          onChange={(v) => setMode(v as Mode)}
          options={[
            { value: 'split', label: 'Side-by-side' },
            { value: 'inline', label: 'Inline' },
          ]}
        />
      </div>

      {/* Column labels */}
      <div className="mt-4 flex items-center gap-2 text-2xs">
        <span className="inline-flex items-center gap-1.5 font-mono text-danger-ink">
          <span className="h-2 w-2 rounded-full bg-danger" /> {from.id}
        </span>
        <span className="text-muted">→</span>
        <span className="inline-flex items-center gap-1.5 font-mono text-success-ink">
          <span className="h-2 w-2 rounded-full bg-success" /> {to.id}
        </span>
      </div>

      <div
        key={`${mode}-${target}`}
        className="scroll-slim mt-2 overflow-x-auto rounded-xl border border-border bg-surface-2/30 animate-fade-in"
      >
        {mode === 'inline' ? (
          <pre className="min-w-max font-mono text-xs leading-relaxed">
            {ops.map((op, i) => (
              <div
                key={i}
                className={classNames(
                  'flex gap-3 px-3 py-0.5',
                  op.type === 'add' && 'bg-success/10',
                  op.type === 'remove' && 'bg-danger/10',
                )}
              >
                <span
                  className={classNames(
                    'w-3 shrink-0 select-none text-center',
                    op.type === 'add' && 'text-success-ink',
                    op.type === 'remove' && 'text-danger-ink',
                    op.type === 'equal' && 'text-transparent',
                  )}
                >
                  {op.type === 'add' ? '+' : op.type === 'remove' ? '−' : '·'}
                </span>
                <span
                  className={classNames(
                    op.type === 'add' && 'text-success-ink',
                    op.type === 'remove' && 'text-danger-ink',
                    op.type === 'equal' && 'text-ink-soft',
                  )}
                >
                  {op.text || ' '}
                </span>
              </div>
            ))}
          </pre>
        ) : (
          <div className="min-w-max divide-y divide-border/60 font-mono text-xs leading-relaxed">
            {rows.map((row, i) => {
              const leftChanged = row.left !== null && row.type !== 'equal';
              const rightChanged = row.right !== null && row.type !== 'equal';
              return (
                <div key={i} className="grid grid-cols-2">
                  <div
                    className={classNames(
                      'border-r border-border px-3 py-0.5',
                      leftChanged ? 'bg-danger/10 text-danger-ink' : 'text-ink-soft',
                    )}
                  >
                    {row.left ?? '\u00A0'}
                  </div>
                  <div
                    className={classNames(
                      'px-3 py-0.5',
                      rightChanged ? 'bg-success/10 text-success-ink' : 'text-ink-soft',
                    )}
                  >
                    {row.right ?? '\u00A0'}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </Card>
  );
}
