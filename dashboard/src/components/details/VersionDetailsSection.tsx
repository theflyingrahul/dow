import { useStore } from '../../store/AppStore';
import { Button } from '../ui/Button';
import { Reveal } from '../ui/Reveal';
import { TagBadge } from '../ui/Badge';
import { VersionSelect } from '../ui/VersionSelect';
import { IconBranch, IconCompare } from '../ui/icons';
import { formatTimestamp } from '../../lib/format';
import { ConfigSection } from './ConfigSection';
import { OutputsSection } from './OutputsSection';
import { MetricsSection } from './MetricsSection';

function DetailHeader() {
  const { versions, versionsById, selectedId, select, setView, setCompareFrom, setCompareTo } =
    useStore();
  const version = versionsById[selectedId];
  const parent = version?.parentId ? versionsById[version.parentId] : null;
  if (!version) return null;

  const tail = version.label.replace(new RegExp(`^${version.id}\\s*·?\\s*`), '');

  const goCompare = () => {
    if (parent) {
      setCompareFrom(parent.id);
      setCompareTo(version.id);
    }
    setView('compare');
  };

  return (
    <div className="panel relative overflow-hidden p-6">
      <div aria-hidden="true" className="pointer-events-none absolute inset-0 bg-brand-sheen opacity-60" />
      <div className="relative flex flex-col gap-6 lg:flex-row lg:items-start lg:justify-between">
        <div className="min-w-0">
          <h2 className="font-display text-3xl font-semibold tracking-tight sm:text-4xl">
            <span className="text-brand">{version.id}</span>{' '}
            <span className="text-2xl text-ink-soft sm:text-3xl">{tail}</span>
          </h2>

          {/* One compact metadata line: tags · author · time · changed field · parent */}
          <div className="mt-3 flex flex-wrap items-center gap-x-2.5 gap-y-2 text-2xs text-muted">
            {version.tags.length > 0 ? (
              version.tags.map((t) => <TagBadge key={t} tag={t} />)
            ) : (
              <span>untagged</span>
            )}
            <span aria-hidden="true">·</span>
            <span>
              by <span className="font-semibold text-ink-soft">{version.author}</span>
            </span>
            <span aria-hidden="true">·</span>
            <span>{formatTimestamp(version.createdAt)}</span>
            <span aria-hidden="true">·</span>
            <span>
              changed{' '}
              {version.changedField ? (
                <span className="font-mono font-semibold text-ink">{version.changedField}</span>
              ) : (
                <span>root · baseline</span>
              )}
            </span>
            {parent && (
              <button
                type="button"
                onClick={() => select(parent.id)}
                className="focus-ring inline-flex items-center gap-1 rounded-md text-brand hover:underline"
              >
                <IconBranch className="h-3.5 w-3.5" />
                from {parent.id}
              </button>
            )}
          </div>

          {version.summary && version.summary !== tail && (
            <p className="mt-3 max-w-xl text-sm leading-relaxed text-ink-soft">{version.summary}</p>
          )}
        </div>

        <div className="flex shrink-0 flex-col gap-3 lg:w-64">
          <VersionSelect
            label="Inspecting"
            value={selectedId}
            versions={versions}
            onChange={select}
            dotClassName="bg-brand"
          />
          <Button
            variant="secondary"
            block
            onClick={goCompare}
            iconLeft={<IconCompare className="h-4 w-4" />}
          >
            {parent ? `Compare vs ${parent.id}` : 'Open Compare'}
          </Button>
        </div>
      </div>
    </div>
  );
}

export function VersionDetailsSection() {
  const { versionsById, selectedId } = useStore();
  const version = versionsById[selectedId];
  const parent = version?.parentId ? versionsById[version.parentId] : null;
  if (!version) return null;

  return (
    <div className="space-y-5 lg:space-y-6">
      <Reveal>
        <DetailHeader />
      </Reveal>

      <Reveal index={1}>
        <MetricsSection version={version} parent={parent} />
      </Reveal>

      <Reveal index={2}>
        <OutputsSection version={version} />
      </Reveal>

      <Reveal index={3}>
        <ConfigSection version={version} />
      </Reveal>
    </div>
  );
}
