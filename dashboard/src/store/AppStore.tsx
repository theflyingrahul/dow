import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useState,
  type ReactNode,
} from 'react';
import type {
  MetricSet,
  NewRunInput,
  OutputSample,
  ServerComparison,
  Version,
  ViewKey,
} from '../types';
import type { Dataset } from '../data/loadData';
import { averageAdjacentDrift } from '../lib/drift';

// ---- deterministic helpers for synthesizing a "New Version" --------- //

const clamp01 = (x: number) => Math.max(0, Math.min(1, x));

function hashString(s: string): number {
  let h = 2166136261;
  for (let i = 0; i < s.length; i++) {
    h ^= s.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  return h >>> 0;
}

/** Small seeded PRNG so synthesized runs are stable for a given input. */
function mulberry32(seed: number): () => number {
  let a = seed;
  return () => {
    a |= 0;
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function buildSamples(texts: string[], baseTokens: number, baseLatency: number): OutputSample[] {
  return texts.map((output, i) => ({
    id: `s${i + 1}`,
    output,
    tokens: Math.round(baseTokens + ((i * 7) % 13) - 6),
    latencyMs: Math.round(baseLatency + ((i * 53) % 140) - 70),
  }));
}

/** Synthesize a believable child version from the New Version form input. */
function synthesizeVersion(base: Version, input: NewRunInput, id: string): Version {
  const rand = mulberry32(hashString(id + input.note + input.temperature));
  const jitter = (scale: number) => (rand() - 0.5) * scale;

  const tempDelta = input.temperature - base.config.sampling.temperature;
  const isHosted = input.provider !== 'mock';

  const metrics: MetricSet = {
    accuracy: clamp01(base.metrics.accuracy - Math.abs(tempDelta) * 0.08 + jitter(0.03)),
    rougeL: clamp01(base.metrics.rougeL - Math.abs(tempDelta) * 0.04 + jitter(0.02)),
    stability: clamp01(base.metrics.stability - tempDelta * 0.3 + jitter(0.04)),
    hallucinationRate: clamp01(
      base.metrics.hallucinationRate + Math.max(0, tempDelta) * 0.12 + jitter(0.02),
    ),
    latencyMs: Math.max(
      400,
      (isHosted ? 1300 : 950) + (input.maxTokens - 192) * 0.8 + jitter(120),
    ),
    costUsd: Math.max(
      0.0005,
      (isHosted ? 0.0082 : 0.0021) * (input.samples / 5) * (input.maxTokens / 192) + jitter(0.0006),
    ),
    tokenUsage: Math.max(
      40,
      base.metrics.tokenUsage + (input.maxTokens - base.config.sampling.maxTokens) * 0.2 + tempDelta * 18,
    ),
    avgWordCount: Math.max(6, base.metrics.avgWordCount + tempDelta * 3 + jitter(1.5)),
  };

  // Vary the base outputs proportionally to temperature so the diff + drift
  // respond to the chosen settings.
  const pool = base.outputs.map((o) => o.output);
  const texts: string[] = [];
  for (let i = 0; i < input.samples; i++) {
    let text = pool[i % pool.length];
    if (input.temperature >= 0.8 && i % 2 === 1) {
      text = text.replace(/the customer/i, 'an unhappy customer');
    }
    if (input.temperature >= 0.6 && i % 3 === 0) {
      text = text.replace(/an update\.?$/i, 'a status update and a delivery date.');
    }
    texts.push(text);
  }

  return {
    id,
    label: `${id} · new version`,
    parentId: base.id,
    createdAt: new Date().toISOString(),
    author: 'you',
    summary: input.note.trim() || `New version branched from ${base.id}.`,
    changedField: tempDelta !== 0 ? 'sampling.temperature' : 'sampling.maxTokens',
    tags: ['experimental'],
    status: 'captured',
    config: {
      ...base.config,
      model: { ...base.config.model, provider: input.provider, name: input.modelName },
      sampling: {
        ...base.config.sampling,
        temperature: input.temperature,
        maxTokens: input.maxTokens,
      },
      evaluation: { ...base.config.evaluation, samples: input.samples },
    },
    outputs: buildSamples(texts, metrics.tokenUsage, metrics.latencyMs),
    metrics,
  };
}

function nextVersionId(versions: Version[]): string {
  const max = versions.reduce((acc, v) => {
    const n = Number(v.id.replace(/\D/g, ''));
    return Number.isFinite(n) ? Math.max(acc, n) : acc;
  }, 0);
  return `v${max + 1}`;
}

// ---- store ---------------------------------------------------------- //

interface AppStore {
  versions: Version[];
  versionsById: Record<string, Version>;
  headId: string;
  /** True when rendering live data from the dow store (not mock data). */
  isLive: boolean;
  /** Engine-computed comparisons keyed `"<fromId>><toId>"` (live mode). */
  serverComparisons: Record<string, ServerComparison>;
  /** Lookup a precomputed real comparison for an ordered version pair. */
  comparisonFor: (fromId: string, toId: string) => ServerComparison | null;
  /** Mean parent→child drift, used as the trend baseline in Compare. */
  typicalDrift: number;

  selectedId: string;
  select: (id: string) => void;

  view: ViewKey;
  setView: (v: ViewKey) => void;

  compareFromId: string;
  compareToId: string;
  setCompareFrom: (id: string) => void;
  setCompareTo: (id: string) => void;
  swapCompare: () => void;

  isNewRunOpen: boolean;
  openNewRun: () => void;
  closeNewRun: () => void;
  /** The previewed, not-yet-committed version (shown after eval, before commit). */
  draftVersion: Version | null;
  /** Synthesize and score the working spec without committing it (preview). */
  previewNewRun: (input: NewRunInput) => void;
  /** Commit the current preview as a new version and open it. */
  commitPreview: () => void;
  /** Discard the preview and return to editing the spec. */
  discardPreview: () => void;

  /** Live server accepts spec edits + commits (vs read-only live or mock). */
  editable: boolean;
  /** Active spec name, and its raw YAML when served live (for the editor). */
  specName: string | null;
  specText: string | null;
  isSpecEditorOpen: boolean;
  openSpecEditor: () => void;
  closeSpecEditor: () => void;
}

const StoreContext = createContext<AppStore | null>(null);

export function AppStoreProvider({
  dataset,
  children,
}: {
  dataset: Dataset;
  children: ReactNode;
}) {
  const [versions, setVersions] = useState<Version[]>(dataset.versions);
  const [selectedId, setSelectedId] = useState<string>(dataset.selectedId);
  const [view, setView] = useState<ViewKey>('dashboard');
  const [compareFromId, setCompareFromId] = useState<string>(dataset.compareFromId);
  const [compareToId, setCompareToId] = useState<string>(dataset.compareToId);
  const [isNewRunOpen, setNewRunOpen] = useState(false);
  const [draftVersion, setDraftVersion] = useState<Version | null>(null);
  const [isSpecEditorOpen, setSpecEditorOpen] = useState(false);

  const headId = dataset.headId;

  const versionsById = useMemo(
    () => Object.fromEntries(versions.map((v) => [v.id, v])) as Record<string, Version>,
    [versions],
  );

  // Live data ships engine-computed drift; mock data derives it client-side.
  const typicalDrift = useMemo(
    () => (dataset.live ? dataset.typicalDrift : averageAdjacentDrift(versions)),
    [dataset.live, dataset.typicalDrift, versions],
  );

  const comparisonFor = useCallback(
    (fromId: string, toId: string): ServerComparison | null =>
      dataset.comparisons[`${fromId}>${toId}`] ?? null,
    [dataset.comparisons],
  );

  // Selecting a version drives both Version Details and the Compare panel.
  const select = useCallback(
    (id: string) => {
      setSelectedId(id);
      setCompareToId(id);
      const parent = versionsById[id]?.parentId;
      if (parent) setCompareFromId(parent);
      else setCompareFromId((prev) => (prev === id ? headId : prev));
    },
    [versionsById, headId],
  );

  const swapCompare = useCallback(() => {
    setCompareFromId(compareToId);
    setCompareToId(compareFromId);
  }, [compareFromId, compareToId]);

  // Preview: synthesize and score the working spec without committing it, so the
  // result can be reviewed (and tweaked) before it becomes a version.
  const previewNewRun = useCallback(
    (input: NewRunInput) => {
      const base = versionsById[input.baseVersionId];
      if (!base) {
        setNewRunOpen(false);
        return;
      }
      const id = nextVersionId(versions);
      setDraftVersion(synthesizeVersion(base, input, id));
    },
    [versions, versionsById],
  );

  // Commit the previewed draft as a real version and open it in Version Details.
  const commitPreview = useCallback(() => {
    if (!draftVersion) return;
    const created = draftVersion;
    setVersions((prev) => [...prev, created]);
    setSelectedId(created.id);
    setCompareFromId(created.parentId ?? headId);
    setCompareToId(created.id);
    setView('details');
    setNewRunOpen(false);
    setDraftVersion(null);
  }, [draftVersion, headId]);

  const discardPreview = useCallback(() => setDraftVersion(null), []);

  const value = useMemo<AppStore>(
    () => ({
      versions,
      versionsById,
      headId,
      isLive: dataset.live,
      serverComparisons: dataset.comparisons,
      comparisonFor,
      typicalDrift,
      selectedId,
      select,
      view,
      setView,
      compareFromId,
      compareToId,
      setCompareFrom: setCompareFromId,
      setCompareTo: setCompareToId,
      swapCompare,
      isNewRunOpen,
      openNewRun: () => setNewRunOpen(true),
      closeNewRun: () => {
        setNewRunOpen(false);
        setDraftVersion(null);
      },
      draftVersion,
      previewNewRun,
      commitPreview,
      discardPreview,
      editable: dataset.editable,
      specName: dataset.specName,
      specText: dataset.specText,
      isSpecEditorOpen,
      openSpecEditor: () => setSpecEditorOpen(true),
      closeSpecEditor: () => setSpecEditorOpen(false),
    }),
    [
      versions,
      versionsById,
      headId,
      dataset.live,
      dataset.comparisons,
      comparisonFor,
      typicalDrift,
      selectedId,
      select,
      view,
      compareFromId,
      compareToId,
      swapCompare,
      isNewRunOpen,
      draftVersion,
      previewNewRun,
      commitPreview,
      discardPreview,
      dataset.editable,
      dataset.specName,
      dataset.specText,
      isSpecEditorOpen,
    ],
  );

  return <StoreContext.Provider value={value}>{children}</StoreContext.Provider>;
}

export function useStore(): AppStore {
  const ctx = useContext(StoreContext);
  if (!ctx) throw new Error('useStore must be used within an AppStoreProvider');
  return ctx;
}
