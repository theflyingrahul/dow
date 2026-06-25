import type { MetricDescriptor } from '../../types';
import { HEADLINE_METRICS, METRICS_BY_KEY } from '../../data/metrics';
import { useStore } from '../../store/AppStore';
import { lineageMetricSeries } from '../../lib/tree';
import { classNames, formatDelta, formatMetricByDescriptor } from '../../lib/format';
import { Card } from '../ui/Card';
import { Reveal } from '../ui/Reveal';
import { Sparkline } from '../ui/Sparkline';
import { IconArrowDown, IconArrowUp } from '../ui/icons';

type DeltaTone = 'success' | 'danger' | 'neutral';

function deltaTone(delta: number, betterWhen: MetricDescriptor['betterWhen']): DeltaTone {
  if (Math.abs(delta) < 1e-9) return 'neutral';
  const improved = betterWhen === 'higher' ? delta > 0 : delta < 0;
  return improved ? 'success' : 'danger';
}

const TONE_TEXT: Record<DeltaTone, string> = {
  success: 'text-success-ink',
  danger: 'text-danger-ink',
  neutral: 'text-muted',
};
const TONE_SPARK: Record<DeltaTone, string> = {
  success: 'text-success',
  danger: 'text-danger',
  neutral: 'text-brand',
};

interface MetricCardProps {
  descriptor: MetricDescriptor;
  value: number | undefined;
  delta: number | null;
  series: number[];
}

/** Reusable metric card: value, delta-vs-parent, and a lineage sparkline. */
export function MetricCard({ descriptor, value, delta, series }: MetricCardProps) {
  const tone: DeltaTone = delta === null ? 'neutral' : deltaTone(delta, descriptor.betterWhen);
  const rising = (delta ?? 0) > 0;

  return (
    <Card hover className="flex h-full flex-col p-4">
      <div className="flex items-center justify-between gap-2">
        <p className="kicker">{descriptor.label}</p>
        {delta === null ? (
          <span className="text-2xs font-semibold text-muted">baseline</span>
        ) : (
          <span
            className={classNames(
              'inline-flex items-center gap-0.5 text-2xs font-semibold',
              TONE_TEXT[tone],
            )}
          >
            {Math.abs(delta) > 1e-9 &&
              (rising ? (
                <IconArrowUp className="h-3 w-3" />
              ) : (
                <IconArrowDown className="h-3 w-3" />
              ))}
            {formatDelta(delta, descriptor.format)}
          </span>
        )}
      </div>

      <div className="mt-3 flex items-end justify-between gap-3">
        <div className="min-w-0">
          <p className="metric-num text-3xl font-semibold leading-none text-ink">
            {value === undefined ? '—' : formatMetricByDescriptor(value, descriptor)}
          </p>
          <p className="mt-1.5 text-2xs text-muted">
            target {formatMetricByDescriptor(descriptor.target, descriptor)}
          </p>
        </div>
        <div className={classNames('shrink-0', TONE_SPARK[tone])}>
          <Sparkline
            data={series}
            width={104}
            height={40}
            ariaLabel={`${descriptor.label} trend across this version's lineage`}
          />
        </div>
      </div>
    </Card>
  );
}

/** Headline metrics row for the currently selected version. */
export function MetricsCards() {
  const { selectedId, versionsById } = useStore();
  const version = versionsById[selectedId];
  const parent = version?.parentId ? versionsById[version.parentId] : null;
  if (!version) return null;

  return (
    <section aria-label="Headline metrics" className="grid grid-cols-2 gap-3 sm:gap-4 lg:grid-cols-4">
      {HEADLINE_METRICS.map((key, i) => {
        const descriptor = METRICS_BY_KEY[key];
        if (!descriptor) return null;
        const value: number | undefined = version.metrics[key];
        const parentValue: number | undefined = parent ? parent.metrics[key] : undefined;
        const delta =
          value !== undefined && parentValue !== undefined ? value - parentValue : null;
        const series = lineageMetricSeries(versionsById, version.id, key);
        return (
          <Reveal key={key} index={i}>
            <MetricCard descriptor={descriptor} value={value} delta={delta} series={series} />
          </Reveal>
        );
      })}
    </section>
  );
}
