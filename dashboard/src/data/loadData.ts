import type { ServerComparison, Version } from '../types';
import { applyMetricRegistry } from './metrics';

/**
 * A fully-resolved dataset the store renders from. Produced either by loading
 * live data from the dow store (`/data.json`) or from the bundled mock data.
 */
export interface Dataset {
  /** True when the data came from a running `dow dashboard` server. */
  live: boolean;
  versions: Version[];
  headId: string;
  selectedId: string;
  compareFromId: string;
  compareToId: string;
  /** Project-typical parent→child drift (real, engine-computed when live). */
  typicalDrift: number;
  /** Precomputed real comparisons, keyed `"<fromId>><toId>"`. */
  comparisons: Record<string, ServerComparison>;
  specName: string | null;
  specs: string[];
}

/** Raw payload shape emitted by `dow dashboard` (dow/dashboard.py). */
interface LivePayload {
  live?: boolean;
  versions?: Version[];
  metricDescriptors?: Parameters<typeof applyMetricRegistry>[0];
  headlineMetrics?: string[];
  comparisons?: Record<string, ServerComparison>;
  typicalDrift?: number;
  headId?: string;
  defaultSelectedId?: string;
  defaultCompareFromId?: string;
  defaultCompareToId?: string;
  specName?: string | null;
  specs?: string[];
}

/**
 * Attempt to load live data from the dow dashboard server. Returns `null` when
 * not served (e.g. `vite dev`, or static preview), so the caller can fall back
 * to mock data. Applies the live metric registry as a side effect on success.
 */
export async function loadLiveData(): Promise<Dataset | null> {
  try {
    const res = await fetch('data.json', { cache: 'no-store' });
    if (!res.ok) return null;
    if (!res.headers.get('content-type')?.includes('application/json')) return null;

    const raw = (await res.json()) as LivePayload;
    const versions = Array.isArray(raw.versions) ? raw.versions : [];
    if (versions.length === 0) return null;

    if (raw.metricDescriptors?.length) {
      applyMetricRegistry(raw.metricDescriptors, raw.headlineMetrics);
    }

    const headId = raw.headId ?? versions[versions.length - 1].id;
    return {
      live: true,
      versions,
      headId,
      selectedId: raw.defaultSelectedId ?? headId,
      compareFromId: raw.defaultCompareFromId ?? headId,
      compareToId: raw.defaultCompareToId ?? headId,
      typicalDrift: typeof raw.typicalDrift === 'number' ? raw.typicalDrift : 0,
      comparisons: raw.comparisons ?? {},
      specName: raw.specName ?? null,
      specs: raw.specs ?? [],
    };
  } catch {
    return null;
  }
}
