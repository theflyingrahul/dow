/**
 * Domain types for the Drift Observation Workbench (dow) dashboard.
 *
 * The unit of versioning is the full *inference specification* (prompt, model
 * identity, sampling settings, evaluation config). Each captured run becomes a
 * named version (v1, v2, …) that forms a tree via parent-child links.
 */

/**
 * Inference provider id. Common values are `mock`, `openai`, `ollama`, and
 * `python`, but any string the store reports is accepted.
 */
export type Provider = string;

/** Free-form label a user can attach to a version (mirrors `dow tag`). */
export type VersionTag = string;

/** Well-known tags that get a distinctive tone/colour; others fall back. */
export type KnownVersionTag = 'baseline' | 'good' | 'golden' | 'bad' | 'experimental';

/** Lifecycle status of a captured version. */
export type RunStatus = 'captured' | 'running' | 'failed';

/** Verdict severity used across badges, gauges and copy. */
export type VerdictLevel = 'pass' | 'warn' | 'fail';

/** Human-facing verdict label, matching the dow CLI vocabulary. */
export type VerdictLabel = 'Consistent' | 'Behavior Drift' | 'Likely Regression';

/** Top-level navigable views in the app shell. */
export type ViewKey = 'dashboard' | 'details' | 'compare';

// ------------------------------------------------------------------ //
// Inference specification
// ------------------------------------------------------------------ //

export interface PromptConfig {
  system: string;
  template: string;
  fewShot: string[];
}

export interface ModelConfig {
  provider: Provider;
  name: string;
  /** Pinned snapshot, never a floating alias. */
  version: string;
  /** Model commit / revision hash for open-weight models. */
  revision: string | null;
}

export interface SamplingConfig {
  temperature: number;
  topP: number;
  maxTokens: number;
  frequencyPenalty: number;
  presencePenalty: number;
  /** Pinned for reproducibility. */
  seed: number;
}

export interface DriftThresholds {
  warn: number;
  fail: number;
}

export interface EvaluationConfig {
  embeddingModel: string;
  /** N samples drawn per version, used for the stability signal. */
  samples: number;
  /** Custom evaluator references, e.g. "evals.py:avg_word_count". */
  metrics: string[];
  thresholds: DriftThresholds;
}

export interface SpecConfig {
  specVersion: number;
  name: string;
  task: string;
  prompt: PromptConfig;
  model: ModelConfig;
  sampling: SamplingConfig;
  evaluation: EvaluationConfig;
  input: string;
}

// ------------------------------------------------------------------ //
// Metrics
// ------------------------------------------------------------------ //

/**
 * Metric identifier. The mock dataset uses a fixed vocabulary, but live data
 * supplies its own keys (stability, custom evaluators, ...), so this is a
 * string keyed by the active metric registry.
 */
export type MetricKey = string;

export type MetricFormat = 'percent' | 'decimal' | 'ms' | 'usd' | 'int';

export interface MetricDescriptor {
  key: MetricKey;
  label: string;
  short: string;
  format: MetricFormat;
  /** Direction of "good": a higher accuracy is better; lower latency is better. */
  betterWhen: 'higher' | 'lower';
  /** Soft target used to color values and gauges. */
  target: number;
  /** Relative weight when synthesizing an overall semantic-drift score. */
  driftWeight: number;
  /** Typical span used to normalize deltas into a 0..1 range. */
  normSpan: number;
  description: string;
}

/**
 * A metric reading for one version. Not every version measures every metric
 * (e.g. a custom evaluator added later), so lookups may be undefined.
 */
export type MetricSet = Record<MetricKey, number>;

// ------------------------------------------------------------------ //
// Outputs + versions
// ------------------------------------------------------------------ //

export interface OutputSample {
  id: string;
  output: string;
  tokens: number;
  latencyMs: number;
}

export interface Version {
  id: string; // e.g. "v3"
  label: string; // display name
  parentId: string | null;
  createdAt: string; // ISO-8601
  author: string;
  /** One-line product copy describing what changed in this version. */
  summary: string;
  /** Causal attribution — which spec field drove the behavior change. */
  changedField: string | null;
  tags: VersionTag[];
  status: RunStatus;
  config: SpecConfig;
  outputs: OutputSample[];
  metrics: MetricSet;
}

// ------------------------------------------------------------------ //
// Comparison (recalculated client-side from mock data)
// ------------------------------------------------------------------ //

export interface MetricContribution {
  key: MetricKey;
  label: string;
  /** Raw delta b - a in metric units. */
  delta: number;
  /** Signed, normalized so positive == regression (worse). */
  oriented: number;
  /** Absolute contribution to the synthesized drift score (0..1). */
  weighted: number;
}

export interface Comparison {
  from: Version;
  to: Version;
  /** 1 − mean text-similarity ratio across aligned sample pairs. */
  outputDifference: number;
  /** Synthesized 0..1 semantic drift derived from outputs + metric deltas. */
  semanticDrift: number;
  stabilityFrom: number;
  stabilityTo: number;
  /** to − from; negative means stability dropped. */
  stabilityDelta: number;
  verdict: VerdictLevel;
  verdictLabel: VerdictLabel;
  rationale: string;
  contributions: MetricContribution[];
  /** Drift trend relative to the project's typical version-to-version drift. */
  trend: 'up' | 'down' | 'flat';
  trendDelta: number;
}

/**
 * A comparison precomputed by the dow engine (server-side), used to show the
 * exact same drift/stability/verdict numbers as `dow compare` in live mode.
 */
export interface ServerComparison {
  outputDifference: number;
  semanticDrift: number;
  stabilityFrom: number;
  stabilityTo: number;
  verdict: VerdictLevel;
  verdictLabel: VerdictLabel;
}

/** Payload from the "New Run" modal used to synthesize a child version. */
export interface NewRunInput {
  baseVersionId: string;
  note: string;
  provider: Provider;
  modelName: string;
  temperature: number;
  maxTokens: number;
  samples: number;
}
