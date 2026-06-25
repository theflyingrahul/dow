import { useId } from 'react';
import type { Version } from '../../types';
import { classNames } from '../../lib/format';
import { IconChevronDown } from './icons';

interface VersionSelectProps {
  label: string;
  value: string;
  versions: Version[];
  onChange: (id: string) => void;
  /** Optional accent dot color class for the current selection. */
  dotClassName?: string;
  className?: string;
}

/** Accessible native-select wrapper for choosing a version. */
export function VersionSelect({
  label,
  value,
  versions,
  onChange,
  dotClassName,
  className,
}: VersionSelectProps) {
  const id = useId();
  return (
    <div className={classNames('min-w-0', className)}>
      <label htmlFor={id} className="kicker mb-1.5 block">
        {label}
      </label>
      <div className="relative">
        {dotClassName && (
          <span
            aria-hidden="true"
            className={classNames(
              'pointer-events-none absolute left-3 top-1/2 h-2.5 w-2.5 -translate-y-1/2 rounded-full',
              dotClassName,
            )}
          />
        )}
        <select
          id={id}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          className={classNames(
            'focus-ring h-11 w-full cursor-pointer appearance-none rounded-xl border border-border bg-surface pr-10 text-sm font-semibold text-ink transition-colors hover:border-brand/40',
            dotClassName ? 'pl-8' : 'pl-3.5',
          )}
        >
          {versions.map((v) => (
            <option key={v.id} value={v.id}>
              {v.id} · {v.summary}
            </option>
          ))}
        </select>
        <IconChevronDown className="pointer-events-none absolute right-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted" />
      </div>
    </div>
  );
}
