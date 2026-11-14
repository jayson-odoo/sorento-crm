'use client';

import { useEffect, useLayoutEffect, useRef, useState } from 'react';
import { ChevronLeft, ChevronRight } from 'lucide-react';
import { useImpersonation } from '@/hooks/useImpersonation';
import { cn } from '@/lib/utils';
import { useIsPhone } from './useViewport';

export const SYSTEM_BANNER_HEIGHT_VAR = '--system-banner-height';

interface BannerSource {
  key: 'offline' | 'impersonation';
  message: string;
  action?: { label: string; onClick: () => void; disabled?: boolean };
}

/**
 * The one banner host (E-4, playbook P16): ONE thin full-width bar above the top bar, warn tint,
 * one line (two on a phone), at most one text button, no close for a still-true state. With
 * several sources it shows the most urgent (offline, then impersonation) with "1 of 2".
 */
export function SystemBanner() {
  const { session, stop, stopping } = useImpersonation();
  const isPhone = useIsPhone();
  const [offline, setOffline] = useState(false);
  const [index, setIndex] = useState(0);
  const barRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    setOffline(typeof navigator !== 'undefined' && navigator.onLine === false);
    const goOffline = () => setOffline(true);
    const goOnline = () => setOffline(false);
    window.addEventListener('offline', goOffline);
    window.addEventListener('online', goOnline);
    return () => {
      window.removeEventListener('offline', goOffline);
      window.removeEventListener('online', goOnline);
    };
  }, []);

  const sources: BannerSource[] = [];
  if (offline) {
    sources.push({ key: 'offline', message: 'You are offline. Changes cannot be saved until the connection returns.' });
  }
  if (session) {
    sources.push({
      key: 'impersonation',
      message: `Viewing as ${session.targetUser.name}`,
      action: { label: 'Exit impersonation', onClick: () => void stop(), disabled: stopping },
    });
  }

  const count = sources.length;
  const current = sources[Math.min(index, Math.max(count - 1, 0))];
  const position = Math.min(index, Math.max(count - 1, 0));

  useLayoutEffect(() => {
    const root = document.documentElement;
    if (!barRef.current) {
      root.style.removeProperty(SYSTEM_BANNER_HEIGHT_VAR);
      return;
    }
    root.style.setProperty(SYSTEM_BANNER_HEIGHT_VAR, `${barRef.current.offsetHeight}px`);
    return () => {
      root.style.removeProperty(SYSTEM_BANNER_HEIGHT_VAR);
    };
  }, [count, current?.key, isPhone]);

  if (!current) return null;

  const stepButton = 'inline-flex size-8 shrink-0 items-center justify-center rounded-md hover:bg-warning/20 pointer-coarse:size-11';

  return (
    <div
      ref={barRef}
      role="status"
      data-testid="system-banner"
      data-tone="warn"
      className="sticky inset-x-0 top-0 z-(--z-banner) flex w-full items-center gap-2 border-b border-warning/40 bg-warning/15 px-4 py-1.5 text-sm text-foreground"
    >
      <span
        data-slot="system-banner-message"
        className={cn('min-w-0 flex-1', isPhone ? 'line-clamp-2' : 'truncate')}
      >
        {current.message}
      </span>
      {count > 1 && (
        <>
          <span className="shrink-0 text-xs text-muted-foreground">
            {position + 1} of {count}
          </span>
          <button
            type="button"
            aria-label="Previous banner"
            className={stepButton}
            onClick={() => setIndex((position - 1 + count) % count)}
          >
            <ChevronLeft className="size-4" />
          </button>
          <button
            type="button"
            aria-label="Next banner"
            className={stepButton}
            onClick={() => setIndex((position + 1) % count)}
          >
            <ChevronRight className="size-4" />
          </button>
        </>
      )}
      {current.action && (
        <button
          type="button"
          disabled={current.action.disabled}
          onClick={current.action.onClick}
          className="shrink-0 rounded-md px-2 py-1 text-sm font-medium underline-offset-4 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring pointer-coarse:min-h-11"
        >
          {current.action.label}
        </button>
      )}
    </div>
  );
}
