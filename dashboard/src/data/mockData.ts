import type {
  EvaluationConfig,
  MetricSet,
  ModelConfig,
  OutputSample,
  PromptConfig,
  SamplingConfig,
  SpecConfig,
  Version,
} from '../types';

/**
 * Typed dataset for the dashboard: a Retrieval-Augmented billing assistant.
 * Ten versions form a tree that branches at v3 (→ v4, v5) and v6 (→ v8, v9),
 * then continues v8 → v10 (HEAD). Story:
 *   • v1 baseline (mock retriever + mock model) → v2 temperature bump (drift)
 *   • v3 moves to hosted gpt-4o-mini with real embeddings (quality jump)
 *   • v4 adds strict grounding + citations; v6 upgrades to gpt-4o
 *   • v5 branches to few-shot; v7 over-heats temperature → regression
 *   • v8 is the golden run; v9 tries a local Llama; v10 adds a reranker (HEAD)
 */

const INPUT = 'Why was I charged twice for my Pro plan this month?';

const TEMPLATE =
  'Use the retrieved help-center context to answer the billing question.\n\nContext:\n{context}\n\nQuestion: {input}\n';

const SYSTEM_BASE =
  'You are a billing support assistant. Answer the customer’s question clearly and concisely.';
const SYSTEM_GROUNDED =
  'You are a billing support assistant. Answer only from the retrieved help-center context, cite the relevant policy, and never invent amounts, dates, or policies. If the context does not cover it, say so.';

const FEW_SHOT_PAIRS: string[] = [
  'Q: "I was refunded less than I paid." → A: Refunds are prorated to unused time per the Refund policy; the difference reflects days already used.',
  'Q: "Why did my price go up at renewal?" → A: Promotional pricing ends after the first term; renewals use list price per the Pricing policy.',
];

const EVAL_BASE: EvaluationConfig = {
  embeddingModel: 'hashing-256',
  samples: 5,
  metrics: ['evals.py:avg_answer_length', 'evals.py:cites_source'],
  thresholds: { warn: 0.15, fail: 0.4 },
};

const MOCK_MODEL: ModelConfig = {
  provider: 'mock',
  name: 'mock-rag',
  version: 'mock-2024-09-01',
  revision: null,
};
const GPT_4O_MINI: ModelConfig = {
  provider: 'openai',
  name: 'gpt-4o-mini',
  version: '2024-07-18',
  revision: null,
};
const GPT_4O: ModelConfig = {
  provider: 'openai',
  name: 'gpt-4o',
  version: '2024-08-06',
  revision: null,
};
const LLAMA_LOCAL: ModelConfig = {
  provider: 'ollama',
  name: 'llama-3.1-8b',
  version: 'q4_K_M',
  revision: 'a1b2c3d4',
};

const SAMPLING_BASE: SamplingConfig = {
  temperature: 0.2,
  topP: 1.0,
  maxTokens: 320,
  frequencyPenalty: 0,
  presencePenalty: 0,
  seed: 42,
};

/** Compose a full spec config from sub-parts, applying small overrides. */
function makeConfig(parts: {
  prompt?: Partial<PromptConfig>;
  model?: ModelConfig;
  sampling?: Partial<SamplingConfig>;
  evaluation?: Partial<EvaluationConfig>;
}): SpecConfig {
  return {
    specVersion: 1,
    name: 'billing-rag',
    task: 'Answer a billing question from the knowledge base',
    prompt: {
      system: SYSTEM_BASE,
      template: TEMPLATE,
      fewShot: [],
      ...parts.prompt,
    },
    model: parts.model ?? MOCK_MODEL,
    sampling: { ...SAMPLING_BASE, ...parts.sampling },
    evaluation: { ...EVAL_BASE, ...parts.evaluation },
    input: INPUT,
  };
}

/** Build deterministic per-sample tokens/latency around a mean. */
function toSamples(texts: string[], baseTokens: number, baseLatency: number): OutputSample[] {
  return texts.map((output, i) => ({
    id: `s${i + 1}`,
    output,
    tokens: baseTokens + ((i * 7) % 13) - 6,
    latencyMs: baseLatency + ((i * 53) % 140) - 70,
  }));
}

function metricSet(m: MetricSet): MetricSet {
  return m;
}

// ------------------------------------------------------------------ //
// Versions
// ------------------------------------------------------------------ //

export const VERSIONS: Version[] = [
  {
    id: 'v1',
    label: 'v1 · baseline',
    parentId: null,
    createdAt: '2026-06-15T09:10:00Z',
    author: 'Maya Okafor',
    summary: 'First captured spec — local mock retriever and mock model.',
    changedField: null,
    tags: ['baseline'],
    status: 'captured',
    config: makeConfig({ sampling: { temperature: 0.2 } }),
    outputs: toSamples(
      [
        'It looks like your account was billed twice this month. Duplicate charges are usually a temporary authorization and should drop off within a few days.',
        'You may have been charged twice due to a pending authorization. It typically reverses on its own.',
        'There appear to be two charges on your Pro plan. Please contact support to request a refund for the duplicate.',
        'Double charges can happen during plan changes; the extra charge is usually refunded automatically.',
      ],
      188,
      720,
    ),
    metrics: metricSet({
      accuracy: 0.7,
      rougeL: 0.38,
      stability: 0.74,
      hallucinationRate: 0.12,
      latencyMs: 720,
      costUsd: 0.0015,
      tokenUsage: 188,
      avgWordCount: 34,
    }),
  },
  {
    id: 'v2',
    label: 'v2 · warmer sampling',
    parentId: 'v1',
    createdAt: '2026-06-16T11:24:00Z',
    author: 'Maya Okafor',
    summary: 'Raised temperature to 0.7 to explore answer phrasing.',
    changedField: 'sampling.temperature',
    tags: ['experimental'],
    status: 'captured',
    config: makeConfig({ sampling: { temperature: 0.7 } }),
    outputs: toSamples(
      [
        'Two charges showed up because of how mid-cycle plan changes are billed — one is likely a hold that will clear.',
        'You were probably billed twice due to an overlap between your renewal and a recent change; one should reverse soon.',
        'It seems the system placed an extra charge during your upgrade. Reach out and we can look into a refund.',
        'Mid-month upgrades sometimes create a second charge. It usually corrects itself within a week.',
      ],
      205,
      760,
    ),
    metrics: metricSet({
      accuracy: 0.68,
      rougeL: 0.36,
      stability: 0.6,
      hallucinationRate: 0.15,
      latencyMs: 760,
      costUsd: 0.0017,
      tokenUsage: 205,
      avgWordCount: 40,
    }),
  },
  {
    id: 'v3',
    label: 'v3 · gpt-4o-mini',
    parentId: 'v2',
    createdAt: '2026-06-17T14:02:00Z',
    author: 'Devin Park',
    summary: 'Swapped to hosted gpt-4o-mini with real embeddings.',
    changedField: 'model.name',
    tags: [],
    status: 'captured',
    config: makeConfig({
      model: GPT_4O_MINI,
      sampling: { temperature: 0.5 },
      evaluation: { embeddingModel: 'text-embedding-3-small' },
    }),
    outputs: toSamples(
      [
        'Your Pro plan renewed on the 3rd and a prorated charge for your recent upgrade posted on the 1st, so you see two charges this month. The smaller prorated amount is expected, not a duplicate.',
        'There are two charges because your renewal and a mid-cycle proration landed in the same period. Both are valid under the proration policy.',
        'You were charged for the renewal plus a prorated upgrade difference. If the full amount was duplicated, support can issue a refund.',
        'The two charges reflect your renewal and a proration for upgrading mid-cycle — standard billing behavior.',
      ],
      240,
      1320,
    ),
    metrics: metricSet({
      accuracy: 0.82,
      rougeL: 0.47,
      stability: 0.79,
      hallucinationRate: 0.08,
      latencyMs: 1320,
      costUsd: 0.0071,
      tokenUsage: 240,
      avgWordCount: 44,
    }),
  },
  {
    id: 'v4',
    label: 'v4 · grounded prompt',
    parentId: 'v3',
    createdAt: '2026-06-18T10:18:00Z',
    author: 'Devin Park',
    summary: 'Added strict grounding and citation instructions.',
    changedField: 'prompt.system',
    tags: ['good'],
    status: 'captured',
    config: makeConfig({
      model: GPT_4O_MINI,
      prompt: { system: SYSTEM_GROUNDED },
      sampling: { temperature: 0.4 },
      evaluation: { embeddingModel: 'text-embedding-3-small' },
    }),
    outputs: toSamples(
      [
        'You see two charges because your Pro plan renewed on the 3rd while a prorated upgrade charge posted on the 1st (Billing → Proration policy). The prorated amount is expected; no duplicate was made.',
        'Per the Proration policy, upgrading mid-cycle adds a prorated charge alongside your renewal, which is why two charges appear this month. Both are valid.',
        'Your renewal and a mid-cycle proration both posted this period (Billing → Proration policy). If the full charge was duplicated, we can refund it within 5–7 days.',
        'Two charges appear: the renewal and a prorated upgrade difference (see Proration policy). This is expected and not a duplicate.',
      ],
      232,
      1290,
    ),
    metrics: metricSet({
      accuracy: 0.88,
      rougeL: 0.52,
      stability: 0.84,
      hallucinationRate: 0.04,
      latencyMs: 1290,
      costUsd: 0.0069,
      tokenUsage: 232,
      avgWordCount: 46,
    }),
  },
  {
    id: 'v5',
    label: 'v5 · few-shot',
    parentId: 'v3',
    createdAt: '2026-06-18T16:40:00Z',
    author: 'Lena Fischer',
    summary: 'Branch from v3 — added few-shot billing exemplars.',
    changedField: 'prompt.fewShot',
    tags: ['experimental'],
    status: 'captured',
    config: makeConfig({
      model: GPT_4O_MINI,
      prompt: { fewShot: FEW_SHOT_PAIRS },
      sampling: { temperature: 0.5 },
      evaluation: { embeddingModel: 'text-embedding-3-small' },
    }),
    outputs: toSamples(
      [
        'Your account shows two charges: the Pro renewal and a prorated upgrade fee (Billing → Proration policy). If it is a true duplicate, refunds post in 5–7 business days.',
        'Upgrading mid-cycle adds a prorated charge on top of your renewal, which explains the two line items this month. See the Proration policy for details.',
        'The two charges are your renewal and a proration for the upgrade. Genuine duplicates are refunded within 5–7 days.',
        'Both charges are valid under the Proration policy — renewal plus a prorated upgrade difference. Let us know if you need a refund.',
      ],
      300,
      1520,
    ),
    metrics: metricSet({
      accuracy: 0.85,
      rougeL: 0.55,
      stability: 0.8,
      hallucinationRate: 0.06,
      latencyMs: 1520,
      costUsd: 0.0092,
      tokenUsage: 300,
      avgWordCount: 52,
    }),
  },
  {
    id: 'v6',
    label: 'v6 · gpt-4o',
    parentId: 'v4',
    createdAt: '2026-06-19T13:05:00Z',
    author: 'Devin Park',
    summary: 'Upgraded to gpt-4o for harder billing questions.',
    changedField: 'model.name',
    tags: [],
    status: 'captured',
    config: makeConfig({
      model: GPT_4O,
      prompt: { system: SYSTEM_GROUNDED },
      sampling: { temperature: 0.4 },
      evaluation: { embeddingModel: 'text-embedding-3-small' },
    }),
    outputs: toSamples(
      [
        'You were charged twice because your Pro plan renewed on the 3rd and a prorated upgrade charge posted on the 1st (Billing → Proration policy). The prorated amount is expected and not a duplicate.',
        'Two charges appear this month: your renewal and a mid-cycle proration for upgrading. Both are correct per the Proration policy.',
        'Your renewal and a prorated upgrade difference both posted this period (see Proration policy). If the full amount was duplicated, we will refund it in 5–7 days.',
        'The charges reflect a renewal plus a prorated upgrade (Billing → Proration policy) — expected billing, not a duplicate.',
      ],
      250,
      1680,
    ),
    metrics: metricSet({
      accuracy: 0.92,
      rougeL: 0.57,
      stability: 0.88,
      hallucinationRate: 0.03,
      latencyMs: 1680,
      costUsd: 0.018,
      tokenUsage: 250,
      avgWordCount: 47,
    }),
  },
  {
    id: 'v7',
    label: 'v7 · hot sampling',
    parentId: 'v5',
    createdAt: '2026-06-20T15:48:00Z',
    author: 'Lena Fischer',
    summary: 'Pushed temperature to 1.0 on the few-shot branch.',
    changedField: 'sampling.temperature',
    tags: ['bad'],
    status: 'captured',
    config: makeConfig({
      model: GPT_4O_MINI,
      prompt: { fewShot: FEW_SHOT_PAIRS },
      sampling: { temperature: 1.0 },
      evaluation: { embeddingModel: 'text-embedding-3-small' },
    }),
    outputs: toSamples(
      [
        'You were double-charged $49 due to a known billing glitch this month; I have approved a full refund plus a 10% goodwill credit.',
        'This is a duplicate caused by our payment processor outage on the 2nd — all affected users get an automatic $20 credit.',
        'Two charges means our system billed you twice by mistake; expect both refunded within 24 hours and a free month of Pro.',
        'The extra charge is an error from the new billing migration; I have escalated it and your account will be credited immediately.',
      ],
      330,
      1600,
    ),
    metrics: metricSet({
      accuracy: 0.71,
      rougeL: 0.45,
      stability: 0.53,
      hallucinationRate: 0.17,
      latencyMs: 1600,
      costUsd: 0.0098,
      tokenUsage: 330,
      avgWordCount: 58,
    }),
  },
  {
    id: 'v8',
    label: 'v8 · golden',
    parentId: 'v6',
    createdAt: '2026-06-21T11:30:00Z',
    author: 'Devin Park',
    summary: 'Tightened output and citations — promoted to golden.',
    changedField: 'sampling.maxTokens',
    tags: ['golden'],
    status: 'captured',
    config: makeConfig({
      model: GPT_4O,
      prompt: { system: SYSTEM_GROUNDED },
      sampling: { temperature: 0.3, maxTokens: 256 },
      evaluation: { embeddingModel: 'text-embedding-3-small' },
    }),
    outputs: toSamples(
      [
        'Two charges appear because your Pro plan renewed on the 3rd and a prorated upgrade charge posted on the 1st (Billing → Proration policy). This is expected, not a duplicate. If you were charged the full amount twice, we will refund it within 5–7 business days.',
        'Your renewal and a mid-cycle proration both posted this month (see Proration policy). Both are valid; genuine duplicates are refunded in 5–7 business days.',
        'You see a renewal plus a prorated upgrade difference (Billing → Proration policy) — standard billing. Let us know if the full charge was duplicated and we will process a refund.',
        'The two charges are your renewal and a proration for upgrading mid-cycle (Proration policy). No duplicate was made; reach out if you would like us to review.',
      ],
      236,
      1540,
    ),
    metrics: metricSet({
      accuracy: 0.94,
      rougeL: 0.59,
      stability: 0.9,
      hallucinationRate: 0.02,
      latencyMs: 1540,
      costUsd: 0.0171,
      tokenUsage: 236,
      avgWordCount: 45,
    }),
  },
  {
    id: 'v9',
    label: 'v9 · local llama',
    parentId: 'v6',
    createdAt: '2026-06-22T09:55:00Z',
    author: 'Lena Fischer',
    summary: 'Experiment — local llama-3.1-8b via Ollama.',
    changedField: 'model.provider',
    tags: ['experimental'],
    status: 'captured',
    config: makeConfig({
      model: LLAMA_LOCAL,
      prompt: { system: SYSTEM_GROUNDED },
      sampling: { temperature: 0.4 },
      evaluation: { embeddingModel: 'text-embedding-3-small' },
    }),
    outputs: toSamples(
      [
        'You have two charges because your plan renewed and a prorated upgrade fee was added this cycle (see the Proration policy). The prorated charge is expected.',
        'The renewal and a mid-cycle proration both posted this month, which is why there are two charges. Both are valid.',
        'Upgrading mid-cycle adds a prorated charge alongside your renewal. If it is a real duplicate, support can refund it.',
        'Two charges appear: your renewal and a proration for the upgrade. This follows the Proration policy.',
      ],
      244,
      990,
    ),
    metrics: metricSet({
      accuracy: 0.86,
      rougeL: 0.53,
      stability: 0.82,
      hallucinationRate: 0.05,
      latencyMs: 990,
      costUsd: 0.0001,
      tokenUsage: 244,
      avgWordCount: 48,
    }),
  },
  {
    id: 'v10',
    label: 'v10 · reranker (HEAD)',
    parentId: 'v8',
    createdAt: '2026-06-24T12:21:38Z',
    author: 'you',
    summary: 'Current head — added a cross-encoder reranker.',
    changedField: 'evaluation.embeddingModel',
    tags: [],
    status: 'captured',
    config: makeConfig({
      model: GPT_4O,
      prompt: { system: SYSTEM_GROUNDED },
      sampling: { temperature: 0.3, maxTokens: 256 },
      evaluation: { embeddingModel: 'bge-reranker-base' },
    }),
    outputs: toSamples(
      [
        'You were charged twice because your Pro plan renewed on the 3rd and a prorated upgrade charge posted on the 1st (Billing → Proration policy). This is expected, not a duplicate; if the full amount was billed twice, we will refund it within 5–7 business days.',
        'Two valid charges this month: your renewal and a mid-cycle proration for upgrading (see Proration policy). Genuine duplicates are refunded in 5–7 business days.',
        'Your renewal plus a prorated upgrade difference both posted (Billing → Proration policy) — standard billing. Tell us if you were charged the full amount twice and we will make it right.',
        'The charges reflect a renewal and a proration for your mid-cycle upgrade (Proration policy). No duplicate occurred; we are happy to review if needed.',
      ],
      234,
      1490,
    ),
    metrics: metricSet({
      accuracy: 0.95,
      rougeL: 0.6,
      stability: 0.91,
      hallucinationRate: 0.02,
      latencyMs: 1490,
      costUsd: 0.0168,
      tokenUsage: 234,
      avgWordCount: 45,
    }),
  },
];

/** The version currently "checked out" (mirrors dow's HEAD). */
export const HEAD_VERSION_ID = 'v10';

/** Default selection when the app loads. */
export const DEFAULT_SELECTED_ID = 'v10';

/** Sensible default pairing for the Compare view: golden vs. head. */
export const DEFAULT_COMPARE_FROM_ID = 'v8';
export const DEFAULT_COMPARE_TO_ID = 'v10';
