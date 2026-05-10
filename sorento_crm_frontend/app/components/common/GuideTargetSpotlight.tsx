'use client';

import { useEffect, useRef } from 'react';
import { usePathname, useRouter, useSearchParams } from 'next/navigation';

const SPOTLIGHT_CLASS = 'guide-spotlight';
const SPOTLIGHT_DURATION_MS = 3200;
const RETRY_INTERVAL_MS = 200;
const MAX_RETRIES = 5;

export default function GuideTargetSpotlight() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const target = searchParams?.get('guide_target') ?? null;
  const activeElementRef = useRef<Element | null>(null);
  const clearTimerRef = useRef<number | null>(null);

  useEffect(() => {
    if (!target) return;

    let cancelled = false;
    let retries = 0;
    let retryTimer: number | null = null;
    let stripped = false;

    const stripParam = () => {
      if (stripped) return;
      stripped = true;
      const sp = new URLSearchParams(searchParams?.toString() ?? '');
      sp.delete('guide_target');
      const next = sp.toString();
      router.replace(next ? `${pathname}?${next}` : pathname || '/', { scroll: false });
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

    const tryFind = () => {
      if (cancelled) return;
      const selector = `[data-guide-target="${CSS.escape(target)}"]`;
      const el = document.querySelector(selector);
      if (el) {
        clearActive();
        el.scrollIntoView({ behavior: 'smooth', block: 'center' });
        el.classList.add(SPOTLIGHT_CLASS);
        activeElementRef.current = el;
        clearTimerRef.current = window.setTimeout(() => {
          el.classList.remove(SPOTLIGHT_CLASS);
          if (activeElementRef.current === el) activeElementRef.current = null;
          clearTimerRef.current = null;
        }, SPOTLIGHT_DURATION_MS);
        stripParam();
        return;
      }
      if (retries < MAX_RETRIES) {
        retries += 1;
        retryTimer = window.setTimeout(tryFind, RETRY_INTERVAL_MS);
        return;
      }
      stripParam();
    };

    const rafId = window.requestAnimationFrame(tryFind);

    return () => {
      cancelled = true;
      window.cancelAnimationFrame(rafId);
      if (retryTimer !== null) window.clearTimeout(retryTimer);
    };
  }, [target, pathname, router, searchParams]);

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
