'use client';

import { useCallback, useRef } from 'react';
import { useRouter } from 'next/navigation';

/**
 * `router.prefetch(href)`, at most once per href for the life of the component
 * (PLAN-ui-motion-round2 M4).
 *
 * Shared by every hover-prefetch call site so the "once per href" rule lives
 * in one place: a clickable `DataGrid` row (`LinkableBodyRow`), the detail
 * pager's prev/next neighbours (`useListPager`), and the sidebar menu. All
 * three used to either cold-fetch on click or - the sidebar - carry
 * `prefetch={false}` outright, because a viewport prefetch of ~100 sidebar
 * links was too much; hover is the middle ground.
 */
export function usePrefetchOnce() {
  const router = useRouter();
  const seen = useRef<Set<string>>(new Set());

  return useCallback(
    (href: string) => {
      // A touch device fires `pointerenter` on the tap that is already opening
      // the record, so the prefetch is pure cost there. Asked as `hover: none`
      // rather than `!(hover: hover)` on purpose: a stub matchMedia that
      // answers "no match" to everything - jsdom's, and the one every test in
      // this repo runs against - would read the negative form as "no hover"
      // and switch prefetching off everywhere.
      if (typeof window !== 'undefined' && window.matchMedia?.('(hover: none)').matches) return;
      if (seen.current.has(href)) return;
      seen.current.add(href);
      // Optional: the real `useRouter()` always returns one, but the app has
      // hundreds of tests that mock `next/navigation` with only `push` -
      // this hook reaching every detail pager and every linkable row must not
      // turn every one of them into a `router.prefetch is not a function`.
      router.prefetch?.(href);
    },
    [router],
  );
}
