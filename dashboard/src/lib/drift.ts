import type {
  Comparison,
  MetricContribution,
  MetricKey,
  ServerComparison,
  VerdictLabel,
  VerdictLevel,
  Version,
} from '../types';
import { METRICS, METRICS_BY_KEY } from '../data/metrics';
import { formatDelta } from './format';
import { similarityRatio } from './diff';

const clamp01 = (x: number): number => Math.max(0, Math.min(1, x));

/** Metrics measured by *both* versions (live data may add metrics over time). */
function sharedMetrics(from: Version, to: Version) {
  return METRICS.filter((m) => m.key in from.metrics && m.key in to.metrics);
}

/** 1 − mean text-similarity ratio across aligned sample pairs. */
export function outputDifference(from: Version, to: Version): number {
  const pairs = Math.min(from.outputs.length, to.outputs.length);
  if (pairs === 0) return 0;
  let total = 0;
  for (let i = 0; i < pairs; i++) {
    total += 1 - similarityRatio(from.outputs[i].output, to.outputs[i].output);
  }
  return total / pairs;
}

/**
 * Per-metric delta, normalized and *oriented* so that a positive number always
 * means "worse" (a regression), regardless of whether higher or lower is good.
 */
function metricContribution(key: MetricKey, from: Version, to: Version): MetricContribution {
  const d = METRICS_BY_KEY[key];
  const delta = to.metrics[key] - from.metrics[key];
  const normalized = delta / d.normSpan;
  const oriented = d.betterWhen === 'higher' ? -normalized : normalized;
  const weighted = d.driftWeight * Math.abs(normalized);
  return { key, label: d.label, delta, oriented, weighted };
}

/**
 * Synthesize a 0..1 semantic-drift score from the behavioral signals: half the
 * weight on raw output difference, half on the weighted magnitude of metric
 * change. This is the "mock data function" the gauge and verdict read from.
 */
export function semanticDrift(from: Version, to: Version): number {
  const outDiff = outputDifference(from, to);
  const present = sharedMetrics(from, to);
  const totalWeight = present.reduce((s, m) => s + m.driftWeight, 0);
  const metricDistance = totalWeight
    ? present.reduce((s, m) => s + metricContribution(m.key, from, to).weighted, 0) / totalWeight
    : 0;
  return clamp01(0.5 * outDiff + 0.5 * metricDistance);
}

/**
 * Verdict logic mirrored from dow's metrics engine:
 *   drift ≥ fail  OR stability drop ≥ 0.25  → Likely Regression
 *   drift ≥ warn  OR stability drop ≥ 0.10  → Behavior Drift
 *   otherwise                                → Consistent
 */
function classifyVerdict(
  drift: number,
  stabilityDrop: number,
  warn: number,
  fail: number,
): { level: VerdictLevel; label: VerdictLabel } {
  if (drift >= fail || stabilityDrop >= 0.25) {
    return { level: 'fail', label: 'Likely Regression' };
  }
  if (drift >= warn || stabilityDrop >= 0.1) {
    return { level: 'warn', label: 'Behavior Drift' };
  }
  return { level: 'pass', label: 'Consistent' };
}

function buildRationale(
  level: VerdictLevel,
  drift: number,
  stabilityDelta: number,
  warn: number,
  fail: number,
  contributions: MetricContribution[],
): string {
  const worst = [...contributions].sort((a, b) => b.oriented - a.oriented);
  const best = [...contributions].sort((a, b) => a.oriented - b.oriented);
  const describe = (c: MetricContribution): string =>
    `${c.label.toLowerCase()} ${formatDelta(c.delta, METRICS_BY_KEY[c.key].format)}`;

  if (level === 'fail') {
    const drivers = worst
      .filter((c) => c.oriented > 0.05)
      .slice(0, 2)
      .map(describe);
    const reason =
      drift >= fail
        ? `drift ${(drift * 100).toFixed(1)}% cleared the ${(fail * 100).toFixed(0)}% fail line`
        : `stability fell ${(Math.abs(stabilityDelta) * 100).toFixed(1)}%`;
    return `Likely regression: ${reason}${
      drivers.length ? `, driven by ${drivers.join(' and ')}` : ''
    }. Review before promoting.`;
  }

  if (level === 'warn') {
    const drivers = worst
      .filter((c) => c.oriented > 0.03)
      .slice(0, 2)
      .map(describe);
    return `Behavior shifted: drift ${(drift * 100).toFixed(1)}% is past the ${(warn * 100).toFixed(
      0,
    )}% warn line${drivers.length ? `, mostly ${drivers.join(' and ')}` : ''}. Worth a look.`;
  }

  const gains = best
    .filter((c) => c.oriented < -0.03)
    .slice(0, 2)
    .map(describe);
  return `Consistent: drift held at ${(drift * 100).toFixed(1)}%, under the ${(warn * 100).toFixed(
    0,
  )}% warn line${gains.length ? `, with gains in ${gains.join(' and ')}` : ''}.`;
}

/** Mean parent→child drift across the tree — the baseline for the trend arrow. */
export function averageAdjacentDrift(versions: Version[]): number {
  const byId = new Map(versions.map((v) => [v.id, v]));
  const drifts: number[] = [];
  for (const v of versions) {
    if (!v.parentId) continue;
    const parent = byId.get(v.parentId);
    if (parent) drifts.push(semanticDrift(parent, v));
  }
  if (drifts.length === 0) return 0;
  return drifts.reduce((s, d) => s + d, 0) / drifts.length;
}

export interface CompareOptions {
  /** Project-typical adjacent drift, used to derive the trend indicator. */
  typicalDrift?: number;
  /** Real engine comparison (live mode); overrides client-side estimates. */
  override?: ServerComparison;
}

/** Full client-side comparison between two versions. */
export function compareVersions(from: Version, to: Version, opts: CompareOptions = {}): Comparison {
  const { override } = opts;
  const contributions = sharedMetrics(from, to)
    .map((m) => metricContribution(m.key, from, to))
    .sort((a, b) => b.weighted - a.weighted);

  const outDiff = override ? override.outputDifference : outputDifference(from, to);
  const drift = override ? override.semanticDrift : semanticDrift(from, to);
  const stabilityFrom = override ? override.stabilityFrom : from.metrics.stability;
  const stabilityTo = override ? override.stabilityTo : to.metrics.stability;
  const stabilityDelta = stabilityTo - stabilityFrom;

  const { warn, fail } = to.config.evaluation.thresholds;
  const { level, label } = override
    ? { level: override.verdict, label: override.verdictLabel }
    : classifyVerdict(drift, stabilityFrom - stabilityTo, warn, fail);
  const rationale = buildRationale(level, drift, stabilityDelta, warn, fail, contributions);

  let trend: Comparison['trend'] = 'flat';
  let trendDelta = 0;
  if (opts.typicalDrift && opts.typicalDrift > 0) {
    trendDelta = drift - opts.typicalDrift;
    if (drift > opts.typicalDrift * 1.08) trend = 'up';
    else if (drift < opts.typicalDrift * 0.92) trend = 'down';
  }

  return {
    from,
    to,
    outputDifference: outDiff,
    semanticDrift: drift,
    stabilityFrom,
    stabilityTo,
    stabilityDelta,
    verdict: level,
    verdictLabel: label,
    rationale,
    contributions,
    trend,
    trendDelta,
  };
}
