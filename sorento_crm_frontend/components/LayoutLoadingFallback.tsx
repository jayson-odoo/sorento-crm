'use client';

import { useEffect, useState } from 'react';
import { Skeleton } from '@/components/ui/skeleton';
import { toAbsoluteUrl } from '@/lib/helpers';

/**
 * Shown while the client providers chunk is loading.
 *
 * It used to be a spinner on an empty screen, which threw the app away and put
 * it back: the sidebar and header vanished, then reappeared, and the reader's
 * place went with them. Now it draws the shell it is about to be replaced by -
 * a sidebar column with the logo in it, a header bar - and skeletons only the
 * content pane (S7-04), so the swap is the pane filling in rather than the page
 * being rebuilt.
 *
 * The two measurements are hard-coded because they have to be: `--sidebar-width`
 * and `--header-height` live under the `.demo1` class that the layout adds to
 * `<body>`, and the layout is exactly what has not loaded yet. Their source of
 * truth is `css/demos/demo1.css`; if that changes, this follows.
 *
 * After 10s a "Try refreshing" hint appears, to recover from ChunkLoadError
 * timeouts.
 */
export function LayoutLoadingFallback() {
  const [showRetry, setShowRetry] = useState(false);

  useEffect(() => {
    const t = setTimeout(() => setShowRetry(true), 10000);
    return () => clearTimeout(t);
  }, []);

  return (
    <div
      className="fixed inset-0 z-50 flex bg-background text-foreground"
      role="status"
      aria-label="Loading"
    >
      {/* The sidebar column. Hidden below lg, where the real one is a drawer. */}
      <div className="hidden w-[280px] shrink-0 flex-col border-e border-border lg:flex">
        <div className="flex h-[70px] items-center px-5">
          <img
            className="h-[30px] max-w-none"
            src={toAbsoluteUrl('/media/app/sorento-logo.svg')}
            alt="Sorento"
          />
        </div>
        <div className="space-y-3 px-5 py-4">
          {Array.from({ length: 9 }).map((_, index) => (
            <Skeleton key={index} className="h-4 w-full" />
          ))}
        </div>
      </div>

      <div className="flex min-w-0 grow flex-col">
        <div className="flex h-[60px] shrink-0 items-center justify-between gap-3 border-b border-border px-4 lg:h-[70px] lg:px-6">
          <Skeleton className="h-[30px] w-[110px] lg:hidden" />
          <Skeleton className="hidden h-4 w-40 lg:block" />
          <div className="flex items-center gap-2">
            <Skeleton className="h-8 w-8 rounded-full" />
            <Skeleton className="h-8 w-8 rounded-full" />
          </div>
        </div>

        <div className="grow space-y-5 px-4 py-5 lg:px-6">
          <Skeleton className="h-6 w-56" />
          <div className="space-y-3 rounded-xl border border-border p-5">
            {Array.from({ length: 8 }).map((_, index) => (
              <Skeleton key={index} className="h-4 w-full" />
            ))}
          </div>
          {showRetry && (
            <p className="text-center text-sm text-muted-foreground">
              Taking a while?{' '}
              <button
                type="button"
                onClick={() => window.location.reload()}
                className="underline focus:outline-none focus:ring-2 focus:ring-primary"
              >
                Refresh the page
              </button>
            </p>
          )}
        </div>
      </div>
    </div>
  );
}
