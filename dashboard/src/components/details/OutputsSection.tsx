import { useRef, useState } from 'react';
import type { Version } from '../../types';
import { formatMetric, formatPercent, classNames } from '../../lib/format';
import { Card, CardHeader } from '../ui/Card';
import { Badge } from '../ui/Badge';
import { IconDoc } from '../ui/icons';

export function OutputsSection({ version }: { version: Version }) {
  const [active, setActive] = useState(0);
  const tabRefs = useRef<(HTMLButtonElement | null)[]>([]);
  const outputs = version.outputs;
  const current = outputs[Math.min(active, outputs.length - 1)];

  // Reflect stability: how many other samples produced the identical text.
  const duplicates = outputs.filter((o, i) => i !== active && o.output === current?.output).length;

  const focusTab = (i: number) => {
    const next = (i + outputs.length) % outputs.length;
    setActive(next);
    tabRefs.current[next]?.focus();
  };

  return (
    <Card className="flex h-full flex-col p-5">
      <CardHeader
        kicker="Samples"
        title="Outputs"
        icon={<IconDoc className="h-5 w-5" />}
        actions={
          <Badge tone="brand">stability {formatPercent(version.metrics.stability)}</Badge>
        }
      />

      <p className="mt-1 text-2xs text-muted">
        {outputs.length} samples drawn · seed {version.config.sampling.seed}
      </p>

      {/* Tabs */}
      <div
        role="tablist"
        aria-label="Model output samples"
        className="mt-4 flex flex-wrap gap-1.5"
      >
        {outputs.map((o, i) => {
          const selected = i === active;
          return (
            <button
              key={o.id}
              ref={(el) => (tabRefs.current[i] = el)}
              role="tab"
              id={`out-tab-${version.id}-${i}`}
              aria-selected={selected}
              aria-controls={`out-panel-${version.id}-${i}`}
              tabIndex={selected ? 0 : -1}
              onClick={() => setActive(i)}
              onKeyDown={(e) => {
                if (e.key === 'ArrowRight') {
                  e.preventDefault();
                  focusTab(i + 1);
                } else if (e.key === 'ArrowLeft') {
                  e.preventDefault();
                  focusTab(i - 1);
                }
              }}
              className={classNames(
                'focus-ring rounded-lg px-3 py-1.5 text-2xs font-semibold transition-all duration-200',
                selected
                  ? 'bg-brand text-brand-ink shadow-card'
                  : 'bg-surface-2 text-muted hover:text-ink',
              )}
            >
              Sample {i + 1}
            </button>
          );
        })}
      </div>

      {/* Panel */}
      {current && (
        <div
          key={active}
          role="tabpanel"
          id={`out-panel-${version.id}-${active}`}
          aria-labelledby={`out-tab-${version.id}-${active}`}
          tabIndex={0}
          className="focus-ring mt-3 flex flex-1 flex-col rounded-xl border border-border bg-surface-2/40 p-4 animate-fade-in"
        >
          <p className="font-display text-lg leading-relaxed text-ink">&ldquo;{current.output}&rdquo;</p>

          <div className="mt-auto flex flex-wrap items-center gap-x-5 gap-y-2 pt-4 text-2xs text-muted">
            <span className="inline-flex items-center gap-1.5">
              <span className="font-semibold text-ink-soft">{current.tokens}</span> tokens
            </span>
            <span className="inline-flex items-center gap-1.5">
              <span className="font-semibold text-ink-soft">
                {formatMetric(current.latencyMs, 'ms')}
              </span>{' '}
              latency
            </span>
            {duplicates > 0 && (
              <Badge tone="success">matches {duplicates} other{duplicates > 1 ? 's' : ''}</Badge>
            )}
          </div>
        </div>
      )}
    </Card>
  );
}
