import type { ReactNode } from 'react';
import { classNames } from '../../lib/format';
import type { VerdictLevel, VersionTag } from '../../types';

export type BadgeTone = 'neutral' | 'brand' | 'success' | 'warning' | 'danger' | 'accent';

const TONES: Record<BadgeTone, string> = {
  neutral: 'bg-surface-2 text-ink-soft ring-1 ring-inset ring-border',
  brand: 'bg-brand/12 text-brand ring-1 ring-inset ring-brand/25',
  success: 'bg-success/14 text-success-ink ring-1 ring-inset ring-success/30',
  warning: 'bg-warning/16 text-warning-ink ring-1 ring-inset ring-warning/30',
  danger: 'bg-danger/14 text-danger-ink ring-1 ring-inset ring-danger/30',
  accent: 'bg-accent/14 text-accent ring-1 ring-inset ring-accent/30',
};

interface BadgeProps {
  tone?: BadgeTone;
  children: ReactNode;
  icon?: ReactNode;
  className?: string;
  uppercase?: boolean;
}

export function Badge({ tone = 'neutral', children, icon, className, uppercase }: BadgeProps) {
  return (
    <span
      className={classNames(
        'inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-2xs font-semibold',
        uppercase && 'uppercase tracking-wide',
        TONES[tone],
        className,
      )}
    >
      {icon}
      {children}
    </span>
  );
}

export const VERDICT_TONE: Record<VerdictLevel, BadgeTone> = {
  pass: 'success',
  warn: 'warning',
  fail: 'danger',
};

const TAG_TONE: Record<string, BadgeTone> = {
  baseline: 'neutral',
  good: 'success',
  golden: 'accent',
  bad: 'danger',
  experimental: 'brand',
};

/** Renders a version tag with a consistent tone. */
export function TagBadge({ tag }: { tag: VersionTag }) {
  return (
    <Badge tone={TAG_TONE[tag] ?? 'neutral'} uppercase>
      {tag}
    </Badge>
  );
}
