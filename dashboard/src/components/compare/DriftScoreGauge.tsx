import { useEffect, useState } from 'react';
import type { Comparison, VerdictLevel } from '../../types';
import { formatPercent, classNames } from '../../lib/format';
import { IconArrowDown, IconArrowRight, IconArrowUp } from '../ui/icons';

const LEVEL_VAR: Record<VerdictLevel, string> = {
  pass: '--success',
  warn: '--warning',
  fail: '--danger',
};

const R = 80;
const CX = 100;
const CY = 100;
const ARC_LEN = Math.PI * R; // semicircle length

/** Cartesian point at fraction f (0 = left, 1 = right) along the top semicircle. */
function pointAt(f: number): { x: number; y: number } {
  const angle = (180 - 180 * f) * (Math.PI / 180);
  return { x: CX + R * Math.cos(angle), y: CY - R * Math.sin(angle) };
}

function Tick({ fraction, label }: { fraction: number; label: string }) {
  const outer = (() => {
    const p = pointAt(fraction);
    const angle = (180 - 180 * fraction) * (Math.PI / 180);
    return {
      x1: CX + (R - 11) * Math.cos(angle),
      y1: CY - (R - 11) * Math.sin(angle),
      x2: CX + (R + 11) * Math.cos(angle),
      y2: CY - (R + 11) * Math.sin(angle),
      lx: CX + (R + 20) * Math.cos(angle),
      ly: CY - (R + 20) * Math.sin(angle),
      tx: p.x,
    };
  })();
  return (
    <g>
      <line
        x1={outer.x1}
        y1={outer.y1}
        x2={outer.x2}
        y2={outer.y2}
        stroke="rgb(var(--ink) / 0.35)"
        strokeWidth={1.5}
        strokeLinecap="round"
      />
      <text
        x={outer.lx}
        y={outer.ly}
        textAnchor="middle"
        dominantBaseline="middle"
        className="fill-muted font-mono"
        style={{ fontSize: 8 }}
      >
        {label}
      </text>
    </g>
  );
}

export function DriftScoreGauge({ comparison }: { comparison: Comparison }) {
  const { semanticDrift: drift, verdict, trend } = comparison;
  const { warn, fail } = comparison.to.config.evaluation.thresholds;
  const fraction = Math.max(0, Math.min(1, drift));

  // Animate the arc sweep on mount and whenever the value changes.
  const [mounted, setMounted] = useState(false);
  useEffect(() => {
    const id = requestAnimationFrame(() => setMounted(true));
    return () => cancelAnimationFrame(id);
  }, []);

  const offset = mounted ? ARC_LEN * (1 - fraction) : ARC_LEN;
  const colorVar = LEVEL_VAR[verdict];

  const TrendIcon = trend === 'up' ? IconArrowUp : trend === 'down' ? IconArrowDown : IconArrowRight;
  const trendText =
    trend === 'up' ? 'above typical drift' : trend === 'down' ? 'below typical drift' : 'typical drift';
  const trendTone =
    trend === 'up' ? 'text-danger-ink' : trend === 'down' ? 'text-success-ink' : 'text-muted';

  return (
    <div className="flex flex-col items-center">
      <div className="relative w-full max-w-[20rem]">
        <svg viewBox="0 0 200 132" className="w-full" role="img" aria-label={`Semantic drift ${formatPercent(drift)}`}>
          {/* Track */}
          <path
            d={`M ${CX - R} ${CY} A ${R} ${R} 0 0 1 ${CX + R} ${CY}`}
            fill="none"
            stroke="rgb(var(--surface-3))"
            strokeWidth={14}
            strokeLinecap="round"
          />
          {/* Value arc */}
          <path
            d={`M ${CX - R} ${CY} A ${R} ${R} 0 0 1 ${CX + R} ${CY}`}
            fill="none"
            stroke={`rgb(var(${colorVar}))`}
            strokeWidth={14}
            strokeLinecap="round"
            strokeDasharray={ARC_LEN}
            strokeDashoffset={offset}
            style={{ transition: 'stroke-dashoffset 1s cubic-bezier(0.22,1,0.36,1)' }}
          />
          <Tick fraction={warn} label="warn" />
          <Tick fraction={fail} label="fail" />
        </svg>

        {/* Center readout */}
        <div className="absolute inset-x-0 bottom-1 flex flex-col items-center">
          <span
            className="font-display text-5xl font-semibold leading-none tracking-tight"
            style={{ color: `rgb(var(${colorVar}))` }}
          >
            {(drift * 100).toFixed(1)}
            <span className="text-2xl">%</span>
          </span>
          <span className="kicker mt-1">semantic drift</span>
        </div>
      </div>

      <div
        className={classNames(
          'mt-3 inline-flex items-center gap-1.5 rounded-full bg-surface-2 px-3 py-1 text-2xs font-semibold',
          trendTone,
        )}
      >
        <TrendIcon className="h-3.5 w-3.5" />
        {trendText}
      </div>

      {/* Threshold legend */}
      <div className="mt-3 flex items-center gap-4 text-2xs text-muted">
        <span className="inline-flex items-center gap-1.5">
          <span className="h-2 w-2 rounded-full bg-warning" /> warn {warn}
        </span>
        <span className="inline-flex items-center gap-1.5">
          <span className="h-2 w-2 rounded-full bg-danger" /> fail {fail}
        </span>
      </div>
    </div>
  );
}
