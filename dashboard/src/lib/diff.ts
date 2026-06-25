import type { SpecConfig } from '../types';

/**
 * Lightweight text diffing utilities (no dependencies). Used by the Compare
 * view to diff serialized specs and model outputs.
 */

export type DiffType = 'equal' | 'add' | 'remove';

export interface DiffOp {
  type: DiffType;
  text: string;
}

/** A single row in a side-by-side diff (left = from, right = to). */
export interface DiffRow {
  left: string | null;
  right: string | null;
  type: DiffType;
}

/**
 * Classic LCS line diff. Returns an ordered op list (remove before add for a
 * given change) suitable for both inline and side-by-side rendering.
 */
export function diffLines(aLines: string[], bLines: string[]): DiffOp[] {
  const n = aLines.length;
  const m = bLines.length;

  // LCS length table.
  const dp: number[][] = Array.from({ length: n + 1 }, () => new Array(m + 1).fill(0));
  for (let i = n - 1; i >= 0; i--) {
    for (let j = m - 1; j >= 0; j--) {
      dp[i][j] = aLines[i] === bLines[j] ? dp[i + 1][j + 1] + 1 : Math.max(dp[i + 1][j], dp[i][j + 1]);
    }
  }

  const ops: DiffOp[] = [];
  let i = 0;
  let j = 0;
  while (i < n && j < m) {
    if (aLines[i] === bLines[j]) {
      ops.push({ type: 'equal', text: aLines[i] });
      i++;
      j++;
    } else if (dp[i + 1][j] >= dp[i][j + 1]) {
      ops.push({ type: 'remove', text: aLines[i] });
      i++;
    } else {
      ops.push({ type: 'add', text: bLines[j] });
      j++;
    }
  }
  while (i < n) ops.push({ type: 'remove', text: aLines[i++] });
  while (j < m) ops.push({ type: 'add', text: bLines[j++] });
  return ops;
}

/** Convert a flat op list into aligned side-by-side rows. */
export function toSideBySide(ops: DiffOp[]): DiffRow[] {
  const rows: DiffRow[] = [];
  let k = 0;
  while (k < ops.length) {
    const op = ops[k];
    if (op.type === 'equal') {
      rows.push({ left: op.text, right: op.text, type: 'equal' });
      k++;
      continue;
    }
    // Pair a run of removes with the following run of adds.
    if (op.type === 'remove') {
      const removes: string[] = [];
      while (k < ops.length && ops[k].type === 'remove') removes.push(ops[k++].text);
      const adds: string[] = [];
      while (k < ops.length && ops[k].type === 'add') adds.push(ops[k++].text);
      const max = Math.max(removes.length, adds.length);
      for (let r = 0; r < max; r++) {
        rows.push({
          left: r < removes.length ? removes[r] : null,
          right: r < adds.length ? adds[r] : null,
          type: r < removes.length && r < adds.length ? 'remove' : r < removes.length ? 'remove' : 'add',
        });
      }
      continue;
    }
    // Lone adds.
    rows.push({ left: null, right: op.text, type: 'add' });
    k++;
  }
  return rows;
}

/** Counts of added / removed lines for a summary badge. */
export function diffStats(ops: DiffOp[]): { added: number; removed: number } {
  let added = 0;
  let removed = 0;
  for (const op of ops) {
    if (op.type === 'add') added++;
    else if (op.type === 'remove') removed++;
  }
  return { added, removed };
}

/**
 * difflib-style similarity ratio over characters: 2·LCS / (len(a) + len(b)).
 * Returns 1 for identical strings, 0 for fully disjoint. Outputs are short so
 * the O(n·m) table is inexpensive.
 */
export function similarityRatio(a: string, b: string): number {
  if (a === b) return 1;
  const n = a.length;
  const m = b.length;
  if (n === 0 || m === 0) return 0;

  let prev = new Array(m + 1).fill(0);
  let curr = new Array(m + 1).fill(0);
  for (let i = 1; i <= n; i++) {
    for (let j = 1; j <= m; j++) {
      curr[j] = a[i - 1] === b[j - 1] ? prev[j - 1] + 1 : Math.max(prev[j], curr[j - 1]);
    }
    [prev, curr] = [curr, prev];
  }
  const lcs = prev[m];
  return (2 * lcs) / (n + m);
}

/** Render a spec config as diff-friendly, YAML-ish text lines. */
export function serializeSpec(config: SpecConfig): string[] {
  const { prompt, model, sampling, evaluation } = config;
  const fewShot =
    prompt.fewShot.length === 0
      ? ['  few_shot: []']
      : ['  few_shot:', ...prompt.fewShot.map((ex) => `    - ${ex}`)];

  return [
    `name: ${config.name}`,
    `task: ${config.task}`,
    'prompt:',
    `  system: ${prompt.system}`,
    `  template: ${prompt.template.replace(/\n/g, '\\n')}`,
    ...fewShot,
    'model:',
    `  provider: ${model.provider}`,
    `  name: ${model.name}`,
    `  version: ${model.version}`,
    `  revision: ${model.revision ?? 'null'}`,
    'sampling:',
    `  temperature: ${sampling.temperature}`,
    `  top_p: ${sampling.topP}`,
    `  max_tokens: ${sampling.maxTokens}`,
    `  frequency_penalty: ${sampling.frequencyPenalty}`,
    `  presence_penalty: ${sampling.presencePenalty}`,
    `  seed: ${sampling.seed}`,
    'evaluation:',
    `  embedding_model: ${evaluation.embeddingModel}`,
    `  samples: ${evaluation.samples}`,
    `  metrics: [${evaluation.metrics.join(', ')}]`,
    `  drift_warn: ${evaluation.thresholds.warn}`,
    `  drift_fail: ${evaluation.thresholds.fail}`,
  ];
}
