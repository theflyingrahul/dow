import type { Comparison, VerdictLevel } from '../../types';
import { METRICS_BY_KEY } from '../../data/metrics';
import { classNames, formatDelta, formatPercent } from '../../lib/format';
import { Card, CardHeader } from '../ui/Card';
import { IconCheck, IconFail, IconWarning } from '../ui/icons';
import type { ReactNode } from 'react';

const BANNER: Record<VerdictLevel, string> = {
  pass: 'bg-success/12 ring-success/25',
  warn: 'bg-warning/14 ring-warning/30',
  fail: 'bg-danger/12 ring-danger/30',
};
const ICON_WRAP: Record<VerdictLevel, string> = {
  pass: 'bg-success text-white',
  warn: 'bg-warning text-white',
  fail: 'bg-danger text-white',
};
const LABEL_TEXT: Record<VerdictLevel, string> = {
  pass: 'text-success-ink',
  warn: 'text-warning-ink',
  fail: 'text-danger-ink',
};
const ICONS: Record<VerdictLevel, ReactNode> = {
  pass: <IconCheck className="h-6 w-6" />,
  warn: <IconWarning className="h-6 w-6" />,
  fail: <IconFail className="h-6 w-6" />,
};

function Signal({ label, value, tone }: { label: string; value: string; tone?: string }) {
  return (
    <div className="rounded-xl border border-border bg-surface-2/50 px-3 py-2.5">
      <p className="kicker">{label}</p>
      <p className={classNames('metric-num mt-1 text-lg font-semibold', tone ?? 'text-ink')}>
        {value}
      </p>
    </div>
  );
}

export function VerdictCard({ comparison }: { comparison: Comparison }) {
  const { verdict, verdictLabel, rationale, stabilityDelta, outputDifference, semanticDrift } =
    comparison;

  const stabilityTone =
    stabilityDelta > 0.001 ? 'text-success-ink' : stabilityDelta < -0.001 ? 'text-danger-ink' : 'text-ink';

  const drivers = comparison.contributions
    .filter((c) => Math.abs(c.oriented) > 0.02)
    .slice(0, 3);

  return (
    <Card className="flex h-full flex-col p-5">
      <CardHeader kicker="Decision" title="Verdict" />

      <div
        className={classNames(
          'mt-4 flex items-center gap-4 rounded-2xl p-4 ring-1 ring-inset',
          BANNER[verdict],
        )}
      >
        <span className={classNames('grid h-12 w-12 shrink-0 place-items-center rounded-xl', ICON_WRAP[verdict])}>
          {ICONS[verdict]}
        </span>
        <div className="min-w-0">
          <p className="kicker">verdict</p>
          <p className={classNames('font-display text-2xl font-semibold leading-tight', LABEL_TEXT[verdict])}>
            {verdictLabel}
          </p>
        </div>
      </div>

      <p className="mt-4 text-sm leading-relaxed text-ink-soft">{rationale}</p>

      <div className="mt-4 grid grid-cols-3 gap-2.5">
        <Signal label="Drift" value={formatPercent(semanticDrift)} />
        <Signal label="Output diff" value={formatPercent(outputDifference)} />
        <Signal
          label="Stability Δ"
          value={formatDelta(stabilityDelta, 'percent')}
          tone={stabilityTone}
        />
      </div>

      {drivers.length > 0 && (
        <div className="mt-4">
          <p className="kicker mb-2">Top drivers</p>
          <ul className="space-y-1.5">
            {drivers.map((c) => {
              const worse = c.oriented > 0;
              return (
                <li
                  key={c.key}
                  className="flex items-center justify-between gap-3 rounded-lg bg-surface-2/50 px-3 py-1.5"
                >
                  <span className="text-sm text-ink">{c.label}</span>
                  <span className="flex items-center gap-2">
                    <span className="metric-num text-2xs text-ink-soft">
                      {formatDelta(c.delta, METRICS_BY_KEY[c.key].format)}
                    </span>
                    <span
                      className={classNames(
                        'rounded-md px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide',
                        worse ? 'bg-danger/12 text-danger-ink' : 'bg-success/14 text-success-ink',
                      )}
                    >
                      {worse ? 'worse' : 'better'}
                    </span>
                  </span>
                </li>
              );
            })}
          </ul>
        </div>
      )}
    </Card>
  );
}
