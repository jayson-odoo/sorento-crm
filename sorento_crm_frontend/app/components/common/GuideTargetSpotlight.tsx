'use client';

import { useEffect, useRef, useState } from 'react';
import { usePathname, useRouter, useSearchParams } from 'next/navigation';

const SPOTLIGHT_CLASS = 'guide-spotlight';
const SPOTLIGHT_DURATION_MS = 3200;
const RETRY_INTERVAL_MS = 200;
const MAX_RETRIES = 5;
// After the immediate retry window expires (1s), keep watching the DOM for
// the target via MutationObserver — covers buttons that only mount when the
// user opens a dialog. 30s is generous enough for a human to read the chat
// step and click the parent trigger without the spotlight giving up.
const OBSERVER_TIMEOUT_MS = 30_000;

const HASH_PARAM = 'guide_target';
const QUERY_PARAM = 'guide_target';

type TargetSource = 'query' | 'hash';

interface ResolvedTarget {
  value: string;
  source: TargetSource;
}

function parseHashTarget(hash: string | null | undefined): string | null {
  if (!hash) return null;
  // Hash may be "#guide_target=foo" or "#a=1&guide_target=foo&b=2".
  const stripped = hash.startsWith('#') ? hash.slice(1) : hash;
  if (!stripped) return null;
  const parts = stripped.split('&');
  for (const part of parts) {
    const eq = part.indexOf('=');
    if (eq < 0) continue;
    const key = part.slice(0, eq);
    if (key !== HASH_PARAM) continue;
    try {
      return decodeURIComponent(part.slice(eq + 1)) || null;
    } catch {
      return part.slice(eq + 1) || null;
    }
  }
  return null;
}

export default function GuideTargetSpotlight() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const queryTarget = searchParams?.get(QUERY_PARAM) ?? null;

  // Hash isn't part of `useSearchParams`. Track it explicitly via
  // `hashchange` / `popstate` so URLs like `/path#guide_target=X` (the
  // Outline-safe form — Outline's editor strips relative URLs that carry a
  // query string but tolerates fragments) still trigger the spotlight.
  const [hash, setHash] = useState<string | null>(null);
  useEffect(() => {
    if (typeof window === 'undefined') return;
    const update = () => {
      // Next.js can strip the URL fragment during hydration before this
      // component mounts. The root <script> in app/layout.tsx snapshots the
      // initial hash to `window.__GUIDE_TARGET_HASH__` so we can recover it
      // here. Consume + clear it once so subsequent hash changes win.
      const liveHash = window.location.hash || null;
      if (liveHash) {
        setHash(liveHash);
        return;
      }
      let snapshot: string | null = null;
      try {
        snapshot = sessionStorage.getItem('__GUIDE_TARGET_HASH__');
      } catch {
        snapshot = null;
      }
      if (snapshot) {
        try {
          sessionStorage.removeItem('__GUIDE_TARGET_HASH__');
        } catch {
          // ignore
        }
        setHash(snapshot);
        return;
      }
      setHash(null);
    };
    update();
    // The hash snapshot is written by an inline `<script>` in `app/layout.tsx`
    // that runs during HTML parse. Async chunks (React/Next) can race ahead
    // and mount this component BEFORE the inline script executes, so retry
    // briefly until the snapshot appears (or the DOM is fully parsed).
    let retries = 0;
    let retryTimer: number | null = null;
    const retry = () => {
      const liveHash = window.location.hash || null;
      const stashed = (() => {
        try { return sessionStorage.getItem('__GUIDE_TARGET_HASH__'); } catch { return null; }
      })();
      if (liveHash || stashed) {
        update();
        return;
      }
      if (retries < 25) {
        retries += 1;
        retryTimer = window.setTimeout(retry, 80);
      }
    };
    retryTimer = window.setTimeout(retry, 80);
    const onLoad = () => update();
    window.addEventListener('hashchange', update);
    window.addEventListener('popstate', update);
    window.addEventListener('DOMContentLoaded', onLoad);
    window.addEventListener('load', onLoad);
    return () => {
      if (retryTimer !== null) window.clearTimeout(retryTimer);
      window.removeEventListener('hashchange', update);
      window.removeEventListener('popstate', update);
      window.removeEventListener('DOMContentLoaded', onLoad);
      window.removeEventListener('load', onLoad);
    };
  }, [pathname]);

  const resolved: ResolvedTarget | null = (() => {
    if (queryTarget) return { value: queryTarget, source: 'query' };
    const hashTarget = parseHashTarget(hash);
    if (hashTarget) return { value: hashTarget, source: 'hash' };
    return null;
  })();

  const target = resolved?.value ?? null;
  const targetSource = resolved?.source ?? null;
  const activeElementRef = useRef<Element | null>(null);
  const clearTimerRef = useRef<number | null>(null);

  useEffect(() => {
    if (!target) return;

    let cancelled = false;
    let retries = 0;
    let retryTimer: number | null = null;
    let observer: MutationObserver | null = null;
    let observerTimeout: number | null = null;
    let stripped = false;

    const stripParam = () => {
      if (stripped) return;
      stripped = true;
      if (targetSource === 'query') {
        const sp = new URLSearchParams(searchParams?.toString() ?? '');
        sp.delete(QUERY_PARAM);
        const next = sp.toString();
        router.replace(next ? `${pathname}?${next}` : pathname || '/', { scroll: false });
        return;
      }
      // Hash: rebuild the fragment without our key, replace via history so
      // Next's router state stays in sync but we don't trigger a navigation.
      if (typeof window === 'undefined') return;
      const raw = window.location.hash.startsWith('#')
        ? window.location.hash.slice(1)
        : window.location.hash;
      const remaining = raw
        .split('&')
        .filter((part) => part && !part.startsWith(`${HASH_PARAM}=`))
        .join('&');
      const newUrl = `${window.location.pathname}${window.location.search}${remaining ? `#${remaining}` : ''}`;
      window.history.replaceState(null, '', newUrl);
      setHash(remaining ? `#${remaining}` : null);
    };

    const clearActive = () => {
      if (activeElementRef.current) {
        activeElementRef.current.classList.remove(SPOTLIGHT_CLASS);
        activeElementRef.current = null;
      }
      if (clearTimerRef.current !== null) {
        window.clearTimeout(clearTimerRef.current);
        clearTimerRef.current = null;
      }
    };

    const disconnectObserver = () => {
      if (observer) {
        observer.disconnect();
        observer = null;
      }
      if (observerTimeout !== null) {
        window.clearTimeout(observerTimeout);
        observerTimeout = null;
      }
    };

    const applySpotlight = (el: Element) => {
      clearActive();
      el.scrollIntoView({ behavior: 'smooth', block: 'center' });
      el.classList.add(SPOTLIGHT_CLASS);
      activeElementRef.current = el;
      clearTimerRef.current = window.setTimeout(() => {
        el.classList.remove(SPOTLIGHT_CLASS);
        if (activeElementRef.current === el) activeElementRef.current = null;
        clearTimerRef.current = null;
      }, SPOTLIGHT_DURATION_MS);
    };

    const findTarget = (): Element | null => {
      const selector = `[data-guide-target="${CSS.escape(target)}"]`;
      return document.querySelector(selector);
    };

    const startObserver = () => {
      if (cancelled || observer) return;
      observer = new MutationObserver(() => {
        if (cancelled) return;
        const el = findTarget();
        if (el) {
          applySpotlight(el);
          stripParam();
          disconnectObserver();
        }
      });
      observer.observe(document.body, { childList: true, subtree: true });
      observerTimeout = window.setTimeout(() => {
        // Target never appeared. Strip silently.
        disconnectObserver();
        stripParam();
      }, OBSERVER_TIMEOUT_MS);
    };

    const tryFind = () => {
      if (cancelled) return;
      const el = findTarget();
      if (el) {
        applySpotlight(el);
        stripParam();
        return;
      }
      if (retries < MAX_RETRIES) {
        retries += 1;
        retryTimer = window.setTimeout(tryFind, RETRY_INTERVAL_MS);
        return;
      }
      // Quick-retry exhausted — switch to long-watch via MutationObserver so
      // popup-internal targets that mount only after the user opens a dialog
      // still get spotlighted.
      startObserver();
    };

    // Run the first attempt synchronously so a fast effect re-run (caused by
    // any subsequent setState / hash-strip) can't cancel us before rAF fires.
    const immediate = findTarget();
    let rafId = 0;
    if (immediate) {
      applySpotlight(immediate);
      stripParam();
    } else {
      rafId = window.requestAnimationFrame(tryFind);
    }

    return () => {
      cancelled = true;
      if (rafId) window.cancelAnimationFrame(rafId);
      if (retryTimer !== null) window.clearTimeout(retryTimer);
      disconnectObserver();
    };
  }, [target, targetSource, pathname, router, searchParams]);

  useEffect(() => {
    return () => {
      if (activeElementRef.current) {
        activeElementRef.current.classList.remove(SPOTLIGHT_CLASS);
      }
      if (clearTimerRef.current !== null) {
        window.clearTimeout(clearTimerRef.current);
      }
    };
  }, []);

  return null;
}
