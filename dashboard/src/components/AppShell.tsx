import { useState } from 'react';
import { useStore } from '../store/AppStore';
import { Sidebar } from './Sidebar';
import { TopBar } from './TopBar';
import { DashboardSection } from './dashboard/DashboardSection';
import { VersionDetailsSection } from './details/VersionDetailsSection';
import { CompareSection } from './compare/CompareSection';
import { NewRunModal } from './run/NewRunModal';
import { GetStarted } from './run/GetStarted';
import { SpecEditorModal } from './run/SpecEditorModal';

/** Decorative layered background: faint grid + soft brand/accent gradients. */
function BackgroundLayers() {
  return (
    <div aria-hidden="true" className="pointer-events-none fixed inset-0 -z-10 overflow-hidden">
      <div className="absolute inset-0 bg-grid-faint [background-size:44px_44px]" />
      <div className="absolute -left-40 -top-40 h-[28rem] w-[28rem] rounded-full bg-brand/20 blur-[120px]" />
      <div className="absolute -right-32 top-10 h-[24rem] w-[24rem] rounded-full bg-accent/15 blur-[120px]" />
      <div className="absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-brand/40 to-transparent" />
    </div>
  );
}

export function AppShell() {
  const [mobileOpen, setMobileOpen] = useState(false);
  const { view, isLive, versions } = useStore();
  const empty = versions.length === 0;

  return (
    <div className="relative min-h-screen text-ink">
      <BackgroundLayers />

      <div className="relative flex">
        <Sidebar mobileOpen={mobileOpen} onCloseMobile={() => setMobileOpen(false)} />

        <div className="flex min-w-0 flex-1 flex-col">
          <TopBar onOpenMobile={() => setMobileOpen(true)} />

          <main className="mx-auto w-full max-w-[88rem] flex-1 px-4 py-6 sm:px-6 lg:px-8 lg:py-8">
            {/* Keyed wrapper fades content in on view change */}
            <div key={empty ? 'empty' : view} className="animate-fade-in">
              {empty ? (
                <GetStarted />
              ) : (
                <>
                  {view === 'dashboard' && <DashboardSection />}
                  {view === 'details' && <VersionDetailsSection />}
                  {view === 'compare' && <CompareSection />}
                </>
              )}
            </div>
          </main>

          <footer className="border-t border-border px-4 py-6 sm:px-6 lg:px-8">
            <div className="mx-auto flex max-w-[88rem] flex-col items-center justify-between gap-2 text-2xs text-muted sm:flex-row">
              <p>
                <span className="font-display text-sm text-ink">dow</span> · version AI behavior,
                measure drift, catch regressions.
              </p>
              <p className="font-mono">
                {isLive
                  ? 'Live data from your .dow store.'
                  : 'All metrics recomputed client-side from mock data.'}
              </p>
            </div>
          </footer>
        </div>
      </div>

      <NewRunModal />
      <SpecEditorModal />
    </div>
  );
}
