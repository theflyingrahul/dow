import type { ElementType, ReactNode } from 'react';
import { classNames } from '../../lib/format';

interface CardProps {
  as?: ElementType;
  hover?: boolean;
  className?: string;
  children: ReactNode;
  /** Adds the layered brand sheen behind the card content. */
  sheen?: boolean;
}

/** Surface panel used throughout the app. */
export function Card({ as: Tag = 'div', hover, sheen, className, children }: CardProps) {
  return (
    <Tag
      className={classNames(
        'panel relative overflow-hidden',
        hover && 'card-hover',
        className,
      )}
    >
      {sheen && (
        <div
          aria-hidden="true"
          className="pointer-events-none absolute inset-0 bg-brand-sheen opacity-70"
        />
      )}
      <div className="relative">{children}</div>
    </Tag>
  );
}

interface CardHeaderProps {
  kicker?: string;
  title: ReactNode;
  icon?: ReactNode;
  actions?: ReactNode;
  className?: string;
}

/** Editorial card header: kicker label + display title + optional actions. */
export function CardHeader({ kicker, title, icon, actions, className }: CardHeaderProps) {
  return (
    <div className={classNames('flex items-start justify-between gap-4', className)}>
      <div className="min-w-0">
        {kicker && <p className="kicker mb-1">{kicker}</p>}
        <h2 className="flex items-center gap-2 text-lg font-semibold leading-tight text-ink">
          {icon && <span className="text-brand">{icon}</span>}
          <span className="truncate">{title}</span>
        </h2>
      </div>
      {actions && <div className="flex shrink-0 items-center gap-2">{actions}</div>}
    </div>
  );
}
