import { useEffect, useId, useRef, type ReactNode } from 'react';
import { createPortal } from 'react-dom';
import { IconClose } from './icons';
import { classNames } from '../../lib/format';

interface ModalProps {
  open: boolean;
  onClose: () => void;
  title: string;
  description?: string;
  children: ReactNode;
  footer?: ReactNode;
  /** Presentation: centered dialog (default) or right-side drawer. */
  variant?: 'dialog' | 'drawer';
}

const FOCUSABLE =
  'a[href], button:not([disabled]), textarea, input, select, [tabindex]:not([tabindex="-1"])';

/**
 * Accessible modal / drawer with a focus trap, Escape-to-close, scroll lock,
 * and focus restoration. Rendered through a portal on document.body.
 */
export function Modal({
  open,
  onClose,
  title,
  description,
  children,
  footer,
  variant = 'dialog',
}: ModalProps) {
  const panelRef = useRef<HTMLDivElement>(null);
  const titleId = useId();
  const descId = useId();
  const previouslyFocused = useRef<HTMLElement | null>(null);

  useEffect(() => {
    if (!open) return;

    previouslyFocused.current = document.activeElement as HTMLElement;
    const { overflow } = document.body.style;
    document.body.style.overflow = 'hidden';

    // Move focus into the dialog.
    const panel = panelRef.current;
    const focusables = panel?.querySelectorAll<HTMLElement>(FOCUSABLE);
    focusables?.[0]?.focus();

    function onKeyDown(e: KeyboardEvent) {
      if (e.key === 'Escape') {
        e.preventDefault();
        onClose();
        return;
      }
      if (e.key !== 'Tab' || !panel) return;
      const items = Array.from(panel.querySelectorAll<HTMLElement>(FOCUSABLE)).filter(
        (el) => el.offsetParent !== null,
      );
      if (items.length === 0) return;
      const first = items[0];
      const last = items[items.length - 1];
      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault();
        first.focus();
      }
    }

    document.addEventListener('keydown', onKeyDown);
    return () => {
      document.removeEventListener('keydown', onKeyDown);
      document.body.style.overflow = overflow;
      previouslyFocused.current?.focus?.();
    };
  }, [open, onClose]);

  if (!open) return null;

  return createPortal(
    <div
      className="fixed inset-0 z-50 flex"
      // Overlay
    >
      <div
        className="absolute inset-0 bg-ink/40 backdrop-blur-sm animate-fade-in"
        onClick={onClose}
        aria-hidden="true"
      />
      <div
        className={classNames(
          'relative z-10 flex w-full',
          variant === 'drawer' ? 'ml-auto h-full max-w-md' : 'm-auto max-w-lg items-center p-4',
        )}
      >
        <div
          ref={panelRef}
          role="dialog"
          aria-modal="true"
          aria-labelledby={titleId}
          aria-describedby={description ? descId : undefined}
          className={classNames(
            'panel flex w-full flex-col shadow-elevated',
            variant === 'drawer'
              ? 'h-full rounded-none rounded-l-3xl animate-slide-in-right'
              : 'max-h-[90vh] animate-scale-in',
          )}
        >
          <header className="flex items-start justify-between gap-4 border-b border-border p-5">
            <div>
              <h2 id={titleId} className="text-xl font-semibold text-ink">
                {title}
              </h2>
              {description && (
                <p id={descId} className="mt-1 text-sm text-muted">
                  {description}
                </p>
              )}
            </div>
            <button
              type="button"
              onClick={onClose}
              aria-label="Close dialog"
              className="focus-ring -m-1 rounded-lg p-1.5 text-muted transition-colors hover:bg-surface-2 hover:text-ink"
            >
              <IconClose />
            </button>
          </header>

          <div className="scroll-slim flex-1 overflow-y-auto p-5">{children}</div>

          {footer && (
            <footer className="flex items-center justify-end gap-3 border-t border-border p-5">
              {footer}
            </footer>
          )}
        </div>
      </div>
    </div>,
    document.body,
  );
}
