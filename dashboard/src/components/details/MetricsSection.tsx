import type { MetricDescriptor, Version } from '../../types';
import { METRICS } from '../../data/metrics';
import { classNames, formatDelta, formatMetricByDescriptor } from '../../lib/format';
import { Card, CardHeader } from '../ui/Card';
import { IconArrowDown, IconArrowUp, IconGauge } from '../ui/icons';

type Status = 'good' | 'warn' | 'bad';

const FILL: Record<Status, string> = {
  good: 'bg-success',
  warn: 'bg-warning',
  bad: 'bg-danger',
};

const clamp01 = (x: number) => Math.max(0, Math.min(1, x));

function statusOf(value: number, d: MetricDescriptor): Status {
  const ratio = d.betterWhen === 'higher' ? value / d.target : d.target / Math.max(value, 1e-9);
  if (ratio >= 1) return 'good';
  if (ratio >= 0.85) return 'warn';
  return 'bad';
}

function bar(value: number, d: MetricDescriptor): { fill: number; tick: number } {
  if (d.format === 'percent' || d.format === 'decimal') {
    return { fill: clamp01(value), tick: clamp01(d.target) };
  }
  const domainMax = Math.max(value, d.target) * 1.5;
  return { fill: clamp01(value / domainMax), tick: clamp01(d.target / domainMax) };
}

function MetricRow({
  descriptor,
  value,
  delta,
}: {
  descriptor: MetricDescriptor;
  value: number;
  delta: number | null;
}) {
  const status = statusOf(value, descriptor);
  const { fill, tick } = bar(value, descriptor);
  const improved =
    delta === null || Math.abs(delta) < 1e-9
      ? null
      : descriptor.betterWhen === 'higher'
        ? delta > 0
        : delta < 0;

  return (
    <div className="py-3.5">
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          <p className="text-sm font-semibold text-ink">{descriptor.label}</p>
          <p className="mt-0.5 text-2xs leading-snug text-muted">{descriptor.description}</p>
        </div>
        <div className="shrink-0 text-right">
          <p className="metric-num text-lg font-semibold text-ink">
            {formatMetricByDescriptor(value, descriptor)}
          </p>
          {delta !== null && (
            <p
              className={classNames(
                'mt-0.5 inline-flex items-center gap-0.5 text-2xs font-semibold',
                improved === null
                  ? 'text-muted'
                  : improved
                    ? 'text-success-ink'
                    : 'text-danger-ink',
              )}
            >
              {delta > 1e-9 ? (
                <IconArrowUp className="h-3 w-3" />
              ) : delta < -1e-9 ? (
                <IconArrowDown className="h-3 w-3" />
              ) : null}
              {formatDelta(delta, descriptor.format)}
            </p>
          )}
        </div>
      </div>

      <div className="relative mt-2.5 h-2 overflow-hidden rounded-full bg-surface-2">
        <div
          className={classNames('absolute inset-y-0 left-0 rounded-full transition-all duration-700 ease-spring', FILL[status])}
          style={{ width: `${(fill * 100).toFixed(1)}%` }}
        />
        {/* Target marker */}
        <span
          aria-hidden="true"
          className="absolute inset-y-0 w-0.5 -translate-x-1/2 bg-ink/45"
          style={{ left: `${(tick * 100).toFixed(1)}%` }}
          title={`target ${formatMetricByDescriptor(descriptor.target, descriptor)}`}
        />
      </div>
    </div>
  );
}

export function MetricsSection({ version, parent }: { version: Version; parent: Version | null }) {
  return (
    <Card className="p-5">
      <CardHeader
        kicker="Evaluation"
        title="Metric breakdown"
        icon={<IconGauge className="h-5 w-5" />}
        actions={
          parent ? (
            <span className="text-2xs text-muted">
              Δ vs <span className="font-mono text-ink-soft">{parent.id}</span> · ticks mark targets
            </span>
          ) : (
            <span className="text-2xs text-muted">ticks mark targets</span>
          )
        }
      />

      <div className="mt-4 grid gap-x-8 divide-y divide-border sm:grid-cols-2 sm:divide-y-0">
        {METRICS.filter((d) => d.key in version.metrics).map((d) => {
          const value = version.metrics[d.key];
          const parentValue: number | undefined = parent ? parent.metrics[d.key] : undefined;
          const delta = parentValue !== undefined ? value - parentValue : null;
          return <MetricRow key={d.key} descriptor={d} value={value} delta={delta} />;
        })}
      </div>
    </Card>
  );
}
