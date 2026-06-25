import { useEffect, useState } from 'react';
import { AppStoreProvider } from './store/AppStore';
import { AppShell } from './components/AppShell';
import { loadLiveData, type Dataset } from './data/loadData';
import {
  DEFAULT_COMPARE_FROM_ID,
  DEFAULT_COMPARE_TO_ID,
  DEFAULT_SELECTED_ID,
  HEAD_VERSION_ID,
  VERSIONS,
} from './data/mockData';
import { averageAdjacentDrift } from './lib/drift';

/** Bundled demo dataset, used when no live dow server is serving data.json. */
function mockDataset(): Dataset {
  return {
    live: false,
    versions: VERSIONS,
    headId: HEAD_VERSION_ID,
    selectedId: DEFAULT_SELECTED_ID,
    compareFromId: DEFAULT_COMPARE_FROM_ID,
    compareToId: DEFAULT_COMPARE_TO_ID,
    typicalDrift: averageAdjacentDrift(VERSIONS),
    comparisons: {},
    specName: 'billing-rag',
    specs: ['billing-rag'],
  };
}

export default function App() {
  const [dataset, setDataset] = useState<Dataset | null>(null);

  useEffect(() => {
    let active = true;
    loadLiveData().then((live) => {
      if (active) setDataset(live ?? mockDataset());
    });
    return () => {
      active = false;
    };
  }, []);

  if (!dataset) {
    return (
      <div className="grid min-h-screen place-items-center bg-bg text-muted">
        <div className="flex items-center gap-3 text-sm">
          <span className="h-2.5 w-2.5 animate-pulse rounded-full bg-brand" />
          Loading behavior data…
        </div>
      </div>
    );
  }

  return (
    <AppStoreProvider dataset={dataset}>
      <AppShell />
    </AppStoreProvider>
  );
}

