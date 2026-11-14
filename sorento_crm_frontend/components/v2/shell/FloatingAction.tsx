'use client';

import { useEffect, useLayoutEffect, useRef, useState, type RefObject } from 'react';
import { cn } from '@/lib/utils';
import { useIsPhone } from './useViewport';

export const FLOATING_ACTION_ROOM_VAR = '--floating-action-room';

export interface FloatingActionProps {
  /** Same label as the header primary. */
  label: string;
  /** Same handler as the header primary. */
  onAction: () => void;
  /** When set, the action is blocked and the reason is shown instead of acting. */
  blockedReason?: string | null;
  /** The header's primary button; the floating one shows only while this is out of view. */
  headerPrimaryRef: RefObject<HTMLElement | null>;
}

/**
 * The phone primary action (E-3, playbook P4/P5): the page header's primary, repeated at the lower
 * right once the header's own button has scrolled away. Never above 720 px. Pages do not mount this;
 * `PrimaryActionHost` renders the one instance from the registered primary.
 */
export function FloatingAction({ label, onAction, blockedReason, headerPrimaryRef }: FloatingActionProps) {
  const isPhone = useIsPhone();
  // null until the observer has reported: nothing renders before the first answer.
  const [headerInView, setHeaderInView] = useState<boolean | null>(null);
  const [reasonShown, setReasonShown] = useState(false);
  const buttonRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    const el = headerPrimaryRef.current;
    if (!el || typeof IntersectionObserver === 'undefined') return;
    const observer = new IntersectionObserver((entries) => {
      const last = entries[entries.length - 1];
      if (last) setHeaderInView(last.isIntersecting);
    });
    observer.observe(el);
    return () => observer.disconnect();
  }, [headerPrimaryRef]);

  // A reason shown for one block does not outlive it.
  useEffect(() => {
    setReasonShown(false);
  }, [blockedReason]);

  const shown = isPhone && headerInView === false;

  useLayoutEffect(() => {
    const root = document.documentElement;
    if (!shown || !buttonRef.current) {
      root.style.removeProperty(FLOATING_ACTION_ROOM_VAR);
      return;
    }
    root.style.setProperty(FLOATING_ACTION_ROOM_VAR, `${buttonRef.current.offsetHeight + 16}px`);
    return () => root.style.removeProperty(FLOATING_ACTION_ROOM_VAR);
  }, [shown]);

  if (!shown) return null;
  const blocked = Boolean(blockedReason);

  return (
    <>
      {blocked && reasonShown && (
        <div
          role="status"
          className="fixed end-4 bottom-[calc(max(1rem,env(safe-area-inset-bottom))+3.75rem)] z-(--z-banner) max-w-[min(20rem,calc(100vw-2rem))] rounded-md border bg-popover px-3 py-2 text-sm text-popover-foreground shadow-lg"
        >
          {blockedReason}
        </div>
      )}
      <button
        ref={buttonRef}
        type="button"
        data-testid="floating-action"
        aria-disabled={blocked || undefined}
        onClick={() => {
          if (blocked) {
            setReasonShown(true);
            return;
          }
          onAction();
        }}
        className={cn(
          'fixed end-4 bottom-[max(1rem,env(safe-area-inset-bottom))] z-(--z-banner)',
          'inline-flex h-12 min-w-11 items-center justify-center rounded-full px-5 text-sm font-medium shadow-lg',
          'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2',
          blocked ? 'bg-muted text-muted-foreground' : 'bg-primary text-primary-foreground hover:bg-primary/90',
        )}
      >
        {label}
      </button>
    </>
  );
}
