import type { MetricDescriptor, MetricKey } from '../types';

/**
 * Registry of metrics tracked per version. The order here is the canonical
 * display order for the metrics row and the detailed breakdown.
 *
 * `driftWeight` / `normSpan` are used by lib/drift.ts to synthesize an overall
 * semantic-drift score from per-metric deltas (no backend required).
 */
export const METRICS: MetricDescriptor[] = [
  {
    key: 'accuracy',
    label: 'Faithfulness',
    short: 'Acc',
    format: 'percent',
    betterWhen: 'higher',
    target: 0.9,
    driftWeight: 1,
    normSpan: 0.3,
    description: 'Share of answers judged faithful to the retrieved context.',
  },
  {
    key: 'rougeL',
    label: 'ROUGE-L',
    short: 'R-L',
    format: 'decimal',
    betterWhen: 'higher',
    target: 0.55,
    driftWeight: 0.8,
    normSpan: 0.3,
    description: 'Longest-common-subsequence overlap with the reference answer.',
  },
  {
    key: 'stability',
    label: 'Stability',
    short: 'Stab',
    format: 'percent',
    betterWhen: 'higher',
    target: 0.85,
    driftWeight: 1,
    normSpan: 0.4,
    description: 'Mean pairwise self-similarity across N samples of this version.',
  },
  {
    key: 'hallucinationRate',
    label: 'Hallucination',
    short: 'Hall',
    format: 'percent',
    betterWhen: 'lower',
    target: 0.04,
    driftWeight: 1.2,
    normSpan: 0.2,
    description: 'Fraction of answers with claims not grounded in the retrieved context.',
  },
  {
    key: 'latencyMs',
    label: 'Latency',
    short: 'Lat',
    format: 'ms',
    betterWhen: 'lower',
    target: 1400,
    driftWeight: 0.4,
    normSpan: 1500,
    description: 'Median end-to-end response time per sample.',
  },
  {
    key: 'costUsd',
    label: 'Cost / run',
    short: 'Cost',
    format: 'usd',
    betterWhen: 'lower',
    target: 0.012,
    driftWeight: 0.3,
    normSpan: 0.02,
    description: 'Estimated provider spend to draw all samples for this version.',
  },
  {
    key: 'tokenUsage',
    label: 'Tokens',
    short: 'Tok',
    format: 'int',
    betterWhen: 'lower',
    target: 260,
    driftWeight: 0.2,
    normSpan: 400,
    description: 'Mean completion tokens emitted per answer.',
  },
  {
    key: 'avgWordCount',
    label: 'Answer length',
    short: 'Len',
    format: 'int',
    betterWhen: 'higher',
    target: 46,
    driftWeight: 0.2,
    normSpan: 40,
    description: 'Custom evaluator (evals.py:avg_answer_length) — answer verbosity.',
  },
];

export const METRICS_BY_KEY: Record<MetricKey, MetricDescriptor> = METRICS.reduce(
  (acc, m) => {
    acc[m.key] = m;
    return acc;
  },
  {} as Record<MetricKey, MetricDescriptor>,
);

/** Metrics surfaced in the compact dashboard "Metrics Cards" row. */
export const HEADLINE_METRICS: MetricKey[] = [
  'accuracy',
  'stability',
  'hallucinationRate',
  'latencyMs',
];

/**
 * Replace the active metric registry in place. Live data (from the dow store)
 * ships its own descriptors, so the dashboard rebuilds METRICS, METRICS_BY_KEY
 * and HEADLINE_METRICS before rendering. Mutating in place keeps every existing
 * `import { METRICS } from '../data/metrics'` reference valid.
 */
export function applyMetricRegistry(
  descriptors: MetricDescriptor[],
  headline?: MetricKey[],
): void {
  METRICS.splice(0, METRICS.length, ...descriptors);

  for (const key of Object.keys(METRICS_BY_KEY)) delete METRICS_BY_KEY[key];
  for (const descriptor of descriptors) METRICS_BY_KEY[descriptor.key] = descriptor;

  const keys = new Set(descriptors.map((d) => d.key));
  const requested = (headline ?? []).filter((k) => keys.has(k));
  const fallback = descriptors.map((d) => d.key);
  const next = (requested.length ? requested : fallback).slice(0, 4);
  HEADLINE_METRICS.splice(0, HEADLINE_METRICS.length, ...next);
}
