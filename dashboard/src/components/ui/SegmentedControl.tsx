import { useRef, type ReactNode } from 'react';
import { classNames } from '../../lib/format';

export interface SegmentOption<T extends string> {
  value: T;
  label: string;
  icon?: ReactNode;
}

interface SegmentedControlProps<T extends string> {
  options: SegmentOption<T>[];
  value: T;
  onChange: (value: T) => void;
  ariaLabel: string;
  size?: 'sm' | 'md';
  className?: string;
}

/**
 * Accessible segmented toggle (radiogroup). Supports Left/Right arrow keys and
 * animates the active pill with a sliding indicator.
 */
export function SegmentedControl<T extends string>({
  options,
  value,
  onChange,
  ariaLabel,
  size = 'md',
  className,
}: SegmentedControlProps<T>) {
  const refs = useRef<(HTMLButtonElement | null)[]>([]);
  const activeIndex = Math.max(0, options.findIndex((o) => o.value === value));

  const focusAt = (index: number) => {
    const next = (index + options.length) % options.length;
    refs.current[next]?.focus();
    onChange(options[next].value);
  };

  return (
    <div
      role="radiogroup"
      aria-label={ariaLabel}
      className={classNames(
        'relative inline-flex rounded-xl border border-border bg-surface-2 p-1',
        className,
      )}
    >
      {/* Sliding active indicator */}
      <span
        aria-hidden="true"
        className="absolute inset-y-1 rounded-lg bg-surface shadow-card ring-1 ring-border transition-all duration-300 ease-spring"
        style={{
          width: `calc((100% - 0.5rem) / ${options.length})`,
          left: `calc(0.25rem + ${activeIndex} * (100% - 0.5rem) / ${options.length})`,
        }}
      />
      {options.map((opt, i) => {
        const selected = opt.value === value;
        return (
          <button
            key={opt.value}
            ref={(el) => (refs.current[i] = el)}
            role="radio"
            aria-checked={selected}
            tabIndex={selected ? 0 : -1}
            onClick={() => onChange(opt.value)}
            onKeyDown={(e) => {
              if (e.key === 'ArrowRight' || e.key === 'ArrowDown') {
                e.preventDefault();
                focusAt(i + 1);
              } else if (e.key === 'ArrowLeft' || e.key === 'ArrowUp') {
                e.preventDefault();
                focusAt(i - 1);
              }
            }}
            className={classNames(
              'focus-ring relative z-10 inline-flex items-center justify-center gap-1.5 rounded-lg font-semibold transition-colors',
              size === 'sm' ? 'h-7 px-3 text-2xs' : 'h-9 px-4 text-xs',
              selected ? 'text-ink' : 'text-muted hover:text-ink',
            )}
          >
            {opt.icon}
            {opt.label}
          </button>
        );
      })}
    </div>
  );
}
