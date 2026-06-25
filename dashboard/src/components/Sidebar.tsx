import { useStore } from '../store/AppStore';
import type { ViewKey } from '../types';
import { Button } from './ui/Button';
import {
  IconBranch,
  IconClose,
  IconCompare,
  IconDashboard,
  IconDoc,
  IconPlus,
} from './ui/icons';
import { classNames } from '../lib/format';
import type { ReactNode } from 'react';

interface NavDef {
  key: ViewKey;
  label: string;
  hint: string;
  icon: ReactNode;
}

const NAV: NavDef[] = [
  { key: 'dashboard', label: 'Dashboard', hint: 'Tree · history · metrics', icon: <IconDashboard /> },
  { key: 'details', label: 'Version Details', hint: 'Config · outputs · metrics', icon: <IconDoc /> },
  { key: 'compare', label: 'Compare', hint: 'Diff · drift · verdict', icon: <IconCompare /> },
];

function BrandMark() {
  return (
    <div className="flex items-center gap-3">
      <img
        src="/logo.svg"
        alt=""
        width={40}
        height={40}
        className="h-10 w-10 rounded-xl shadow-glow"
      />
      <div className="leading-tight">
        <p className="font-display text-lg font-semibold tracking-tight text-ink">dow</p>
        <p className="text-2xs text-muted">Drift Observation Workbench</p>
      </div>
    </div>
  );
}

function NavItem({ def, active, onSelect }: { def: NavDef; active: boolean; onSelect: () => void }) {
  return (
    <button
      type="button"
      onClick={onSelect}
      aria-current={active ? 'page' : undefined}
      className={classNames(
        'focus-ring group flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-left transition-all duration-200',
        active
          ? 'bg-surface text-ink shadow-card ring-1 ring-border'
          : 'text-ink-soft hover:bg-surface/60 hover:text-ink',
      )}
    >
      <span
        className={classNames(
          'grid h-8 w-8 shrink-0 place-items-center rounded-lg transition-colors',
          active ? 'bg-brand/12 text-brand' : 'text-muted group-hover:text-ink',
        )}
      >
        {def.icon}
      </span>
      <span className="min-w-0">
        <span className="block text-sm font-semibold leading-tight">{def.label}</span>
        <span className="block truncate text-2xs text-muted">{def.hint}</span>
      </span>
    </button>
  );
}

function SidebarInner({ onNavigate }: { onNavigate?: () => void }) {
  const { view, setView, versions, headId, versionsById, openNewRun, editable, specName, openSpecEditor } =
    useStore();
  const head = versionsById[headId];

  return (
    <div className="flex h-full flex-col gap-6 p-5">
      <BrandMark />

      <nav aria-label="Primary" className="flex flex-col gap-1">
        <p className="kicker px-3 pb-1">Workspace</p>
        {NAV.map((def) => (
          <NavItem
            key={def.key}
            def={def}
            active={view === def.key}
            onSelect={() => {
              setView(def.key);
              onNavigate?.();
            }}
          />
        ))}
      </nav>

      {/* Spec summary card */}
      <div className="rounded-2xl border border-border bg-surface/60 p-4">
        <p className="kicker mb-2">Active spec</p>
        <p className="font-mono text-sm font-semibold text-ink">
          {head?.config.name ?? specName ?? '—'}
        </p>
        <p className="mt-0.5 text-2xs leading-relaxed text-muted">{head?.config.task}</p>
        <div className="mt-3 flex items-center gap-3 text-2xs text-muted">
          <span className="inline-flex items-center gap-1">
            <IconBranch className="h-3.5 w-3.5" />
            {versions.length} versions
          </span>
          <span className="inline-flex items-center gap-1 font-mono text-brand">HEAD · {headId}</span>
        </div>
      </div>

      <div className="mt-auto">
        <Button
          variant="primary"
          block
          iconLeft={<IconPlus className="h-4 w-4" />}
          onClick={() => {
            // Live mode edits the real spec + commits; mock mode synthesizes one.
            if (editable) openSpecEditor();
            else openNewRun();
            onNavigate?.();
          }}
        >
          New Version
        </Button>
      </div>
    </div>
  );
}

interface SidebarProps {
  mobileOpen: boolean;
  onCloseMobile: () => void;
}

export function Sidebar({ mobileOpen, onCloseMobile }: SidebarProps) {
  return (
    <>
      {/* Desktop rail */}
      <aside className="sticky top-0 hidden h-screen w-72 shrink-0 border-r border-border bg-bg/80 backdrop-blur lg:block">
        <SidebarInner />
      </aside>

      {/* Mobile drawer */}
      {mobileOpen && (
        <div className="fixed inset-0 z-40 lg:hidden">
          <div
            className="absolute inset-0 bg-ink/40 backdrop-blur-sm animate-fade-in"
            onClick={onCloseMobile}
            aria-hidden="true"
          />
          <aside
            className="absolute left-0 top-0 h-full w-[18rem] max-w-[85vw] border-r border-border bg-bg shadow-elevated animate-slide-in-right"
            aria-label="Primary navigation"
          >
            <button
              type="button"
              onClick={onCloseMobile}
              aria-label="Close navigation"
              className="focus-ring absolute right-3 top-4 z-10 rounded-lg p-1.5 text-muted hover:bg-surface-2 hover:text-ink"
            >
              <IconClose />
            </button>
            <SidebarInner onNavigate={onCloseMobile} />
          </aside>
        </div>
      )}
    </>
  );
}
