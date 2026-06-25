import { forwardRef, type ButtonHTMLAttributes, type ReactNode } from 'react';
import { classNames } from '../../lib/format';

type Variant = 'primary' | 'secondary' | 'ghost' | 'danger';
type Size = 'sm' | 'md' | 'lg';

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: Size;
  iconLeft?: ReactNode;
  iconRight?: ReactNode;
  block?: boolean;
}

const VARIANTS: Record<Variant, string> = {
  primary:
    'bg-brand-solid text-brand-ink shadow-card hover:shadow-glow hover:-translate-y-px active:translate-y-0',
  secondary:
    'bg-surface text-ink border border-border hover:border-brand/40 hover:bg-surface-2',
  ghost: 'bg-transparent text-ink-soft hover:bg-surface-2 hover:text-ink',
  danger: 'bg-danger text-white shadow-card hover:brightness-105 hover:-translate-y-px',
};

const SIZES: Record<Size, string> = {
  sm: 'h-8 px-3 text-2xs gap-1.5',
  md: 'h-10 px-4 text-sm gap-2',
  lg: 'h-12 px-5 text-sm gap-2',
};

/** Primary button primitive with consistent focus ring + motion. */
export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  { variant = 'secondary', size = 'md', iconLeft, iconRight, block, className, children, ...rest },
  ref,
) {
  return (
    <button
      ref={ref}
      className={classNames(
        'focus-ring inline-flex items-center justify-center rounded-xl font-semibold tracking-tight',
        'transition-all duration-200 ease-spring disabled:cursor-not-allowed disabled:opacity-50',
        VARIANTS[variant],
        SIZES[size],
        block && 'w-full',
        className,
      )}
      {...rest}
    >
      {iconLeft}
      {children}
      {iconRight}
    </button>
  );
});
