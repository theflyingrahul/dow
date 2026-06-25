import type { Version } from '../../types';
import { formatMetric, formatPercent } from '../../lib/format';
import { Card, CardHeader } from '../ui/Card';
import { Badge } from '../ui/Badge';
import { IconDoc } from '../ui/icons';

export function OutputsSection({ version }: { version: Version }) {
  const outputs = version.outputs;

  return (
    <Card className="p-5">
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

      {/* Every sample, listed one below another (no tabs to click through). */}
      <ol className="mt-4 space-y-3">
        {outputs.map((o, i) => {
          const duplicates = outputs.filter((x, j) => j !== i && x.output === o.output).length;
          return (
            <li
              key={o.id}
              className="rounded-xl border border-border bg-surface-2/40 p-4"
            >
              <div className="flex items-start gap-3">
                <span className="mt-0.5 shrink-0 rounded-md bg-surface px-2 py-0.5 font-mono text-2xs font-semibold text-muted ring-1 ring-border">
                  {i + 1}
                </span>
                <p className="font-display text-base leading-relaxed text-ink">
                  &ldquo;{o.output}&rdquo;
                </p>
              </div>

              <div className="mt-3 flex flex-wrap items-center gap-x-5 gap-y-2 pl-9 text-2xs text-muted">
                <span className="inline-flex items-center gap-1.5">
                  <span className="font-semibold text-ink-soft">{o.tokens}</span> tokens
                </span>
                <span className="inline-flex items-center gap-1.5">
                  <span className="font-semibold text-ink-soft">
                    {formatMetric(o.latencyMs, 'ms')}
                  </span>{' '}
                  latency
                </span>
                {duplicates > 0 && (
                  <Badge tone="success">matches {duplicates} other{duplicates > 1 ? 's' : ''}</Badge>
                )}
              </div>
            </li>
          );
        })}
      </ol>
    </Card>
  );
}
