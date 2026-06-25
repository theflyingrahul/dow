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
  /** True when served by a live `dow dashboard` that accepts spec edits + commits. */
  editable: boolean;
  /** Raw YAML of the working spec (live mode), for the in-app editor. */
  specText: string | null;
  specPath: string | null;
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
  editable?: boolean;
  specText?: string | null;
  specPath?: string | null;
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

    if (raw.metricDescriptors?.length) {
      applyMetricRegistry(raw.metricDescriptors, raw.headlineMetrics);
    }

    if (versions.length === 0) {
      // A live server with no versions yet (e.g. just after `dow init`): keep the
      // editable live dataset so the UI can show the Get-Started spec editor
      // instead of falling back to the bundled mock data.
      if (!raw.live) return null;
      return {
        live: true,
        versions: [],
        headId: '',
        selectedId: '',
        compareFromId: '',
        compareToId: '',
        typicalDrift: 0,
        comparisons: {},
        specName: raw.specName ?? null,
        specs: raw.specs ?? [],
        editable: raw.editable ?? false,
        specText: raw.specText ?? null,
        specPath: raw.specPath ?? null,
      };
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
      editable: raw.editable ?? false,
      specText: raw.specText ?? null,
      specPath: raw.specPath ?? null,
    };
  } catch {
    return null;
  }
}

// --------------------------------------------------------------------------- //
// write API (live mode): read/save the working spec and capture a version
// --------------------------------------------------------------------------- //
export interface SpecPayload {
  name: string;
  path: string;
  text: string;
}

/** Fetch the current working spec YAML from the live server. */
export async function fetchSpec(): Promise<SpecPayload | null> {
  try {
    const res = await fetch('api/spec', { cache: 'no-store' });
    if (!res.ok) return null;
    return (await res.json()) as SpecPayload;
  } catch {
    return null;
  }
}

/** Save the working spec YAML. `valid` reports whether it parses as a spec. */
export async function saveSpec(
  text: string,
): Promise<{ ok: boolean; valid?: boolean; error?: string | null }> {
  try {
    const res = await fetch('api/spec', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text }),
    });
    return (await res.json()) as { ok: boolean; valid?: boolean; error?: string | null };
  } catch (e) {
    return { ok: false, error: String(e) };
  }
}

/** Capture a version from the current working spec (runs `dow commit`). */
export async function commitVersion(
  message: string,
): Promise<{ ok: boolean; versionId?: string; error?: string }> {
  try {
    const res = await fetch('api/commit', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message }),
    });
    return (await res.json()) as { ok: boolean; versionId?: string; error?: string };
  } catch (e) {
    return { ok: false, error: String(e) };
  }
}
