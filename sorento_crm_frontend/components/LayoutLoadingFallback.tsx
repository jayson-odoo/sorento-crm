'use client';

import { useEffect, useState } from 'react';
import { toAbsoluteUrl } from '@/lib/helpers';

/**
 * Shown while the client providers chunk is loading.
 * After a delay, shows a "Try refreshing" hint to recover from ChunkLoadError timeouts.
 */
export function LayoutLoadingFallback() {
  const [showRetry, setShowRetry] = useState(false);

  useEffect(() => {
    const t = setTimeout(() => setShowRetry(true), 10000);
    return () => clearTimeout(t);
  }, []);

  return (
    <div className="fixed inset-0 z-50 flex min-h-screen w-full flex-col items-center justify-center gap-4 bg-background text-foreground">
      <img
        className="h-[30px] max-w-none"
        src={toAbsoluteUrl('/media/app/sorento-logo.svg')}
        alt="Sorento"
      />
      <div className="h-8 w-8 animate-spin rounded-full border-2 border-primary border-t-transparent" />
      <p className="text-sm text-muted-foreground">Loading…</p>
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
  );
}
