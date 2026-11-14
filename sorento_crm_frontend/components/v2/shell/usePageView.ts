'use client';

import { useEffect, useRef } from 'react';
import { usePathname } from 'next/navigation';
import { apiFetch } from '@/lib/api';

/**
 * Page-view telemetry for UI v2 (D10, UAC D-5). Mounted ONCE, in components/v2/shell/AppShell; v1
 * never mounts it, so v1 sends nothing. The server normalises ids in the route; the client only
 * drops the query and hash.
 */

const URL = '/api/v1/system/page-views';
const BATCH = 10;
const FLUSH_MS = 15_000;
const MAX_MS = 600_000;

export interface PageViewItem {
  route: string;
  viewport: 'phone' | 'tablet' | 'desktop';
  ms_to_first_data: number | null;
  ui_version: 'v2';
  at: string;
}

export function viewportClass(width: number): PageViewItem['viewport'] {
  if (width <= 720) return 'phone';
  if (width <= 1024) return 'tablet';
  return 'desktop';
}

const routeOf = (path: string) => path.split(/[?#]/)[0] || '/';

/** The first route must be recorded this soon after the document started, or the shell was mounted later. */
const FIRST_ROUTE_WINDOW_MS = 10_000;
/** Set once per document: only the document's first navigation has a first paint to report. */
let firstDataReported = false;

/**
 * First contentful paint as a stand-in for "time to first data", for the document's first navigation
 * only. A shell mounted later (a switch from v1, a re-mount) would report a paint from long before it
 * existed, so it sends null instead.
 */
function firstDataMs(isFirst: boolean): number | null {
  if (!isFirst || firstDataReported) return null;
  firstDataReported = true;
  if (typeof performance === 'undefined' || !performance.getEntriesByType) return null;
  if (performance.now() > FIRST_ROUTE_WINDOW_MS) return null;
  const fcp = performance.getEntriesByType('paint').find((e) => e.name === 'first-contentful-paint');
  if (!fcp) return null;
  const ms = Math.round(fcp.startTime);
  return ms >= 0 && ms <= MAX_MS ? ms : null;
}

/** pagehide: the page may be gone before an apiFetch resolves, so plain fetch + keepalive + the bearer token. */
async function sendOnHide(items: PageViewItem[]) {
  try {
    const base = process.env.NEXT_PUBLIC_BASE_PATH || '';
    const tokenRes = await fetch(`${base}/api/auth/token`, { credentials: 'same-origin' });
    if (!tokenRes.ok) return;
    const { token } = (await tokenRes.json()) as { token?: string };
    if (!token) return;
    await fetch(`${base}${URL}`, {
      method: 'POST',
      keepalive: true,
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
      body: JSON.stringify({ items }),
    });
  } catch {
    // Telemetry is best effort.
  }
}

export function usePageView(): void {
  const pathname = usePathname();
  const queue = useRef<PageViewItem[]>([]);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const last = useRef<string | null>(null);

  const take = () => {
    if (timer.current) clearTimeout(timer.current);
    timer.current = null;
    const items = queue.current;
    queue.current = [];
    return items;
  };

  const flush = () => {
    const items = take();
    if (!items.length) return;
    void apiFetch(URL, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ items }),
    }).catch(() => {});
  };
  const flushRef = useRef(flush);
  flushRef.current = flush;

  useEffect(() => {
    const route = routeOf(pathname ?? '/');
    if (route === last.current) return;
    const isFirst = last.current === null;
    last.current = route;
    queue.current.push({
      route,
      viewport: viewportClass(window.innerWidth),
      ms_to_first_data: firstDataMs(isFirst),
      ui_version: 'v2',
      at: new Date().toISOString(),
    });
    if (queue.current.length >= BATCH) flushRef.current();
    else if (!timer.current) timer.current = setTimeout(() => flushRef.current(), FLUSH_MS);
  }, [pathname]);

  useEffect(() => {
    const onHide = () => {
      const items = take();
      if (items.length) void sendOnHide(items);
    };
    window.addEventListener('pagehide', onHide);
    return () => {
      window.removeEventListener('pagehide', onHide);
      // Leaving the v2 shell (a switch to v1) sends what is queued.
      flushRef.current();
    };
  }, []);
}
