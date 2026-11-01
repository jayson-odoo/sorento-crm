'use client';

/**
 * A record's active tab, held in the URL as `?tab=<key>` rather than component state.
 *
 * This is the ONE tab hook for detail pages (NAV-KEEP-TAB, owner ruling 1 Nov 2026: "must stay
 * on the tab when scrolling next and prev"). The record pager (`useListPager`) copies `?tab=` onto
 * every prev/next step, so a page whose tabs read this hook keeps its tab across records for free;
 * Back/forward and a pasted URL open the same tab because the URL is the source of truth.
 *
 * - The default tab writes no `tab` param, so a plain `/x/<id>` link opens on it.
 * - A `?tab=` naming a tab this record does not render (hidden by permission or status, or a tab
 *   the next record simply lacks) shows the default tab. The URL is NOT rewritten: if the tab
 *   arrives a beat later (it is gated on a query that is still loading) it is shown then, and the
 *   next record that does have it opens on it.
 * - `setTab` changes only `tab`; every other query param (the list state the pager walks, a
 *   one-shot `?send=1`) survives untouched.
 *
 * The write goes through `window.history.replaceState`, which Next's app router syncs into
 * `useSearchParams` with no server round trip and no `useRouter` dependency, so a component that
 * renders outside an app router (a unit test) still switches tabs: a local mirror holds the
 * choice until the URL catches up.
 */

import { useState } from 'react';
import { useSearchParams } from 'next/navigation';

export const TAB_PARAM = 'tab';

export interface UseUrlTabOptions<T extends string> {
  /** Every tab id the record renders right now. A `?tab=` outside this list falls back to
   *  `defaultTab`. Omit only when every value is acceptable (the caller validates itself). */
  tabs?: readonly T[];
  /** The tab whose URL carries no `tab` param - the record's landing tab. */
  defaultTab: T;
  /** Accepted for older callers; the URL is now written relative to the current location. */
  basePath?: string;
}

export type SetUrlTab = (tab: string) => void;

/** The URL `tab` would be written as, from the current location. */
export function hrefWithTab(current: URL, tab: string, defaultTab: string): string {
  const url = new URL(current.href);
  if (tab === defaultTab) url.searchParams.delete(TAB_PARAM);
  else url.searchParams.set(TAB_PARAM, tab);
  return `${url.pathname}${url.search}${url.hash}`;
}

/**
 * Returns `[activeTab, setTab]`, the same shape `useState` returns, so it drops straight into
 * `<Tabs value={activeTab} onValueChange={setTab}>`.
 */
export function useUrlTab<T extends string>({
  tabs,
  defaultTab,
}: UseUrlTabOptions<T>): [T, SetUrlTab] {
  const searchParams = useSearchParams();
  const searchKey = searchParams?.toString() ?? '';
  // The tab picked on THIS url. Once the URL moves on (Next synced the write, the pager stepped,
  // back/forward) the URL answers again; until then this mirror does.
  const [picked, setPicked] = useState<{ tab: string; key: string } | null>(null);

  // Once the URL has moved on, the mirror has done its job: drop it, so a later return to
  // the search string it was picked on (a same-record link, a back entry without a remount)
  // reads the URL rather than resurrecting the old pick.
  if (picked && picked.key !== searchKey) setPicked(null);

  const fromUrl = searchParams?.get(TAB_PARAM) ?? null;
  const requested = picked && picked.key === searchKey ? picked.tab : fromUrl;
  const known = (value: string | null): value is T =>
    value != null && (tabs ? (tabs as readonly string[]).includes(value) : value !== '');
  const activeTab: T = known(requested) ? requested : defaultTab;

  const setTab: SetUrlTab = (tab) => {
    setPicked({ tab, key: searchKey });
    if (typeof window === 'undefined') return;
    // `null` state, not `history.state`: Next only syncs a replaceState whose data does not
    // already carry its own `__NA` marker.
    window.history.replaceState(null, '', hrefWithTab(new URL(window.location.href), tab, defaultTab));
  };

  return [activeTab, setTab];
}

/**
 * `href` with `tab` set on it (or left alone for the default tab / no tab). For the few
 * pagers that build their own step href instead of going through `useListPager`, so they
 * carry the open tab the same way (NAV-KEEP-TAB).
 */
export function withTab(href: string, tab: string | null | undefined, defaultTab?: string): string {
  if (!tab || tab === defaultTab) return href;
  const [beforeHash, hash] = href.split('#', 2);
  const [path, query = ''] = beforeHash.split('?', 2);
  const params = new URLSearchParams(query);
  params.set(TAB_PARAM, tab);
  return `${path}?${params.toString()}${hash != null ? `#${hash}` : ''}`;
}
