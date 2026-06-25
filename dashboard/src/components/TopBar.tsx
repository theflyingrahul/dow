import { useStore } from '../store/AppStore';
import type { ViewKey } from '../types';
import { Button } from './ui/Button';
import { ThemeToggle } from './ThemeToggle';
import { IconMenu, IconPlus, IconRefresh, IconSliders } from './ui/icons';

const TITLES: Record<ViewKey, { kicker: string; title: string }> = {
  dashboard: { kicker: 'Overview', title: 'Behavior Dashboard' },
  details: { kicker: 'Inspect', title: 'Version Details' },
  compare: { kicker: 'Diff', title: 'Compare Versions' },
};

export function TopBar({ onOpenMobile }: { onOpenMobile: () => void }) {
  const { view, selectedId, versionsById, setView, openNewRun, isLive, editable, versions, openSpecEditor } =
    useStore();
  const meta = TITLES[view];
  const selected = versionsById[selectedId];
  const refresh = () => window.location.reload();

  return (
    <header className="sticky top-0 z-30 border-b border-border bg-bg/80 backdrop-blur supports-[backdrop-filter]:bg-bg/65">
      <div className="flex h-16 items-center gap-3 px-4 sm:px-6 lg:px-8">
        <button
          type="button"
          onClick={onOpenMobile}
          aria-label="Open navigation"
          className="focus-ring -ml-1 grid h-10 w-10 place-items-center rounded-xl border border-border bg-surface text-ink-soft lg:hidden"
        >
          <IconMenu />
        </button>

        <div className="min-w-0">
          <p className="kicker hidden sm:block">{meta.kicker}</p>
          <h1 className="truncate font-display text-lg font-semibold leading-tight text-ink sm:text-xl">
            {meta.title}
          </h1>
        </div>

        <div className="ml-auto flex items-center gap-2 sm:gap-3">
          {selected && (
            <button
              type="button"
              onClick={() => setView('details')}
              className="focus-ring hidden items-center gap-2 rounded-xl border border-border bg-surface px-3 py-2 text-2xs font-semibold text-ink-soft transition-colors hover:border-brand/40 hover:text-ink md:inline-flex"
              title="Open selected version"
            >
              <span className="h-1.5 w-1.5 rounded-full bg-brand" />
              <span className="font-mono">{selected.id}</span>
              <span className="max-w-[8rem] truncate text-muted">{selected.summary}</span>
            </button>
          )}

          <ThemeToggle />

          {isLive ? (
            <>
              {editable && versions.length > 0 && (
                <Button
                  variant="ghost"
                  onClick={openSpecEditor}
                  iconLeft={<IconSliders className="h-4 w-4" />}
                  className="hidden sm:inline-flex"
                  title="Edit the spec and capture a version"
                >
                  Edit spec
                </Button>
              )}
              <Button
                variant="primary"
                onClick={refresh}
                iconLeft={<IconRefresh className="h-4 w-4" />}
                className="hidden sm:inline-flex"
                title="Re-read the .dow store"
              >
                Refresh
              </Button>
              <Button
                variant="primary"
                onClick={refresh}
                aria-label="Refresh"
                className="sm:hidden"
              >
                <IconRefresh className="h-4 w-4" />
              </Button>
            </>
          ) : (
            <>
              <Button
                variant="primary"
                onClick={openNewRun}
                iconLeft={<IconPlus className="h-4 w-4" />}
                className="hidden sm:inline-flex"
              >
                New Version
              </Button>
              <Button
                variant="primary"
                onClick={openNewRun}
                aria-label="New Version"
                className="sm:hidden"
              >
                <IconPlus className="h-4 w-4" />
              </Button>
            </>
          )}
        </div>
      </div>
    </header>
  );
}
