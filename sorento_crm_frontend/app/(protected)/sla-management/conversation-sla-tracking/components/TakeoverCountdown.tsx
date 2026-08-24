'use client';

import { useEffect, useRef, useState } from 'react';

/** Treat a timezone-less ISO timestamp (naive UTC from the backend) as UTC. */
function asUtc(iso: string): string {
  return /[zZ]|[+-]\d{2}:?\d{2}$/.test(iso) ? iso : `${iso}Z`;
}

/** A depleting countdown bar driven by the server's absolute `commit_at` timestamp
 *  (never a local-only counter - survives refresh). Depletes from full at mount to
 *  empty at `commit_at`, then shows "Finalizing…" until the parent refetch confirms
 *  the commit. Calls `onExpire` once when it crosses zero so the parent can poll. */
export function TakeoverCountdown({
  commitAt,
  windowSeconds,
  onExpire,
  className,
}: {
  commitAt: string | null;
  /** Total cooldown window (s) - fixed bar denominator. Falls back to remaining-at-mount. */
  windowSeconds?: number | null;
  onExpire?: () => void;
  className?: string;
}) {
  // commit_at is naive UTC from the backend (no timezone suffix). new Date() would
  // parse it as LOCAL time - 8h off in UTC+8 - making the bar instantly "Finalizing".
  // Treat a tz-less timestamp as UTC by appending 'Z'.
  const target = commitAt ? Date.parse(asUtc(commitAt)) : 0;
  // Denominator = the FULL window (server-provided) so the bar reflects true progress
  // even after a remount (tab switch). Fall back to remaining-at-mount when absent.
  const maxMsRef = useRef<number>(
    windowSeconds && windowSeconds > 0
      ? windowSeconds * 1000
      : Math.max(1000, target - Date.now()),
  );
  const firedRef = useRef(false);
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 250);
    return () => clearInterval(t);
  }, []);

  useEffect(() => {
    if (!firedRef.current && target > 0 && now >= target) {
      firedRef.current = true;
      onExpire?.();
    }
  }, [now, target, onExpire]);

  const remainingMs = Math.max(0, target - now);
  const pct = Math.max(0, Math.min(100, (remainingMs / maxMsRef.current) * 100));
  const finalizing = remainingMs <= 0;

  const secs = Math.ceil(remainingMs / 1000);
  const mm = Math.floor(secs / 60);
  const ss = secs % 60;
  const label = finalizing ? 'Finalizing…' : `${mm}:${String(ss).padStart(2, '0')}`;

  return (
    <div className={className} aria-label="Takeover countdown" role="timer">
      <div className="flex items-center gap-2">
        <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-muted">
          <div
            className={`h-full rounded-full transition-[width] duration-200 ease-linear ${
              finalizing ? 'bg-muted-foreground/40' : 'bg-primary'
            }`}
            style={{ width: finalizing ? '100%' : `${pct}%` }}
            data-testid="takeover-bar"
          />
        </div>
        <span
          className={`shrink-0 tabular-nums text-xs ${
            finalizing ? 'text-muted-foreground' : 'font-medium'
          }`}
          data-testid="takeover-remaining"
        >
          {label}
        </span>
      </div>
    </div>
  );
}

export default TakeoverCountdown;
