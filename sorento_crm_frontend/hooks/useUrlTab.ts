'use client';

/**
 * A record's active tab, held in the URL rather than component state (S1, AC-A1-A4).
 *
 * Extracted from the loading plan's own inline version (`LoadingPlanView.tsx`, S2 of the
 * loading-plan feedback batch) once the proforma invoice needed the identical behaviour and a
 * second inline copy would have been the second mechanism for one idea. Both records now read
 * this hook.
 *
 * Why the URL and not `useState`: a `useState('general')` forgets the tab on every reload, and
 * the record's own prev/next pager remounts the page component - both threw the reader back to
 * the default tab, which is exactly the bug this hook exists to fix. The default tab itself
 * writes no `?tab=` at all, so a plain `/scm/proforma-invoices/pi-1` link still opens on it.
 */

import { useRouter, useSearchParams } from 'next/navigation';

export interface UseUrlTabOptions<T extends string> {
  /** Every tab id the caller renders, in the order the tab strip shows them. A `?tab=` value
   *  outside this list is not a tab this record has - it falls back to `defaultTab`. */
  tabs: readonly T[];
  /** The tab whose URL carries no `tab` param - the record's landing tab. */
  defaultTab: T;
  /** The record's own path with no query string, e.g. `/scm/proforma-invoices/pi-1`. */
  basePath: string;
}

export type SetUrlTab = (tab: string) => void;

/**
 * Returns `[activeTab, setTab]`, the same shape `useState` returns, so it drops straight into
 * `<Tabs value={activeTab} onValueChange={setTab}>`.
 *
 * `setTab` rewrites every OTHER query param verbatim (`URLSearchParams(searchParams.toString())`
 * copies the lot before the one param it owns is touched), so a list query the pager forwarded
 * onto this URL, or a one-shot param like `?send=1`, survives a tab change untouched.
 */
export function useUrlTab<T extends string>({
  tabs,
  defaultTab,
  basePath,
}: UseUrlTabOptions<T>): [T, SetUrlTab] {
  const router = useRouter();
  const searchParams = useSearchParams();

  const raw = searchParams?.get('tab') ?? null;
  const activeTab: T = raw != null && (tabs as readonly string[]).includes(raw) ? (raw as T) : defaultTab;

  const setTab: SetUrlTab = (tab) => {
    const params = new URLSearchParams(searchParams?.toString());
    if (tab === defaultTab) params.delete('tab');
    else params.set('tab', tab);
    const qs = params.toString();
    router.replace(`${basePath}${qs ? `?${qs}` : ''}`, { scroll: false });
  };

  return [activeTab, setTab];
}
