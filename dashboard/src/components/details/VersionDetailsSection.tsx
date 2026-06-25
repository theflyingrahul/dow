import { useStore } from '../../store/AppStore';
import { Button } from '../ui/Button';
import { Reveal } from '../ui/Reveal';
import { TagBadge } from '../ui/Badge';
import { VersionSelect } from '../ui/VersionSelect';
import { IconBranch, IconCompare } from '../ui/icons';
import { formatTimestamp, humanizeField } from '../../lib/format';
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
          <p className="kicker">Version</p>
          <h2 className="mt-1 font-display text-3xl font-semibold tracking-tight sm:text-4xl">
            <span className="text-brand">{version.id}</span>{' '}
            <span className="text-2xl text-ink-soft sm:text-3xl">{tail}</span>
          </h2>
          <p className="mt-2 max-w-xl text-sm leading-relaxed text-ink-soft">{version.summary}</p>

          <div className="mt-3 flex flex-wrap items-center gap-2">
            {version.tags.length > 0 ? (
              version.tags.map((t) => <TagBadge key={t} tag={t} />)
            ) : (
              <span className="text-2xs text-muted">untagged</span>
            )}
          </div>

          <dl className="mt-4 flex flex-wrap items-center gap-x-6 gap-y-2 text-2xs text-muted">
            <div className="flex items-center gap-1.5">
              <dt className="sr-only">Author</dt>
              <dd>
                by <span className="font-semibold text-ink-soft">{version.author}</span>
              </dd>
            </div>
            <div className="flex items-center gap-1.5">
              <dt className="sr-only">Captured</dt>
              <dd>{formatTimestamp(version.createdAt)}</dd>
            </div>
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
          </dl>

          {/* Causal attribution */}
          <div className="mt-4 inline-flex items-center gap-2 rounded-xl border border-border bg-surface-2/60 px-3 py-2">
            <span className="kicker">changed field</span>
            {version.changedField ? (
              <span className="font-mono text-xs font-semibold text-ink">
                {version.changedField}
              </span>
            ) : (
              <span className="text-xs text-muted">root version · baseline</span>
            )}
            {version.changedField && (
              <span className="text-2xs text-muted">({humanizeField(version.changedField)})</span>
            )}
          </div>
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

      <div className="grid gap-5 lg:grid-cols-12 lg:gap-6">
        <div className="lg:col-span-5">
          <Reveal index={1}>
            <ConfigSection version={version} />
          </Reveal>
        </div>
        <div className="lg:col-span-7">
          <Reveal index={2}>
            <OutputsSection version={version} />
          </Reveal>
        </div>
      </div>

      <Reveal index={3}>
        <MetricsSection version={version} parent={parent} />
      </Reveal>
    </div>
  );
}
