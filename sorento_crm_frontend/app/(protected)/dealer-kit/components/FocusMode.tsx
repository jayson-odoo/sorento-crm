'use client';

import { useEffect } from 'react';
import { Maximize2, Minimize2 } from 'lucide-react';

import { Button } from '@/components/ui/button';

/**
 * Give a canvas the whole window.
 *
 * The page builder and the room designer are the two screens where the app
 * chrome actively costs you: the top bar, the sidebar, the breadcrumb and the
 * page heading together take roughly 200px of height and 280px of width, and
 * both of those are canvas. Everywhere else in the CRM that chrome is how you
 * navigate; here you are working inside one screen for minutes at a time.
 *
 * Implemented by taking the panel OUT of the page flow rather than by hiding the
 * chrome in place. Hiding the shell means reaching across the app to toggle
 * layout state that every other screen shares, and the first regression lands on
 * a page that has nothing to do with the Dealer Kit. A fixed overlay is local,
 * reversible, and cannot leak.
 *
 * Escape exits, because anything that covers the whole window and traps you is
 * worse than the chrome it removed.
 */
export function FocusToggle({
  active,
  onToggle,
  label = 'canvas',
}: {
  active: boolean;
  onToggle: (next: boolean) => void;
  label?: string;
}) {
  return (
    <Button
      variant="outline"
      size="sm"
      aria-pressed={active}
      aria-label={active ? `Exit full screen ${label}` : `Full screen ${label}`}
      onClick={() => onToggle(!active)}
    >
      {active ? <Minimize2 className="size-4" /> : <Maximize2 className="size-4" />}
      {active ? 'Exit full screen' : 'Full screen'}
    </Button>
  );
}

export function FocusShell({
  active,
  onExit,
  children,
}: {
  active: boolean;
  onExit: () => void;
  children: React.ReactNode;
}) {
  useEffect(() => {
    if (!active) return undefined;

    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onExit();
    };
    document.addEventListener('keydown', onKey);

    // The page behind must not scroll while an overlay covers it, or a stray
    // wheel event moves content the user cannot see.
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';

    return () => {
      document.removeEventListener('keydown', onKey);
      document.body.style.overflow = previousOverflow;
    };
  }, [active, onExit]);

  if (!active) return <>{children}</>;

  return (
    <div
      className="fixed inset-0 z-50 flex flex-col gap-3 overflow-auto bg-background p-3"
      data-dk-focus-mode
    >
      {children}
    </div>
  );
}
