'use client';

import { useSyncExternalStore } from 'react';

/** The v2 phone breakpoint (playbook P6/P7, D7): at or below this width the phone layout applies. */
export const PHONE_MAX = 720;

const query = (max: number) => `(max-width: ${max}px)`;

/** True while the viewport is at most `max` px wide. Correct on the first client render. */
export function useMaxWidth(max: number = PHONE_MAX): boolean {
  return useSyncExternalStore(
    (cb) => {
      if (typeof window === 'undefined' || !window.matchMedia) return () => {};
      const mq = window.matchMedia(query(max));
      mq.addEventListener?.('change', cb);
      return () => mq.removeEventListener?.('change', cb);
    },
    () => (typeof window !== 'undefined' && window.matchMedia ? window.matchMedia(query(max)).matches : false),
    () => false,
  );
}

export const useIsPhone = () => useMaxWidth(PHONE_MAX);
