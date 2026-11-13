'use client';

import { useMemo, type ReactNode } from 'react';
import Link from 'next/link';
import { useSearchParams } from 'next/navigation';
import { MoveLeft } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { useRequestScope } from '@/hooks/useRequestScope';
import { isDetailViewKey } from '@/lib/listNavQuery';

export interface BackToListProps {
  /** The list route, e.g. `/order-management/orders`. */
  listPath: string;
  /** e.g. "Back to delivery orders". */
  label: string;
  /**
   * Carry the detail URL's query string back to the list, so it reopens on the
   * same page, sort, search and filters. Off when `listPath` already carries the
   * state it needs (the spec-verification worklist hands over its whole URL).
   */
  appendListState?: boolean;
  className?: string;
  /**
   * A request kind (`useRequestScope`): a limited user of that kind (a salesperson who sees only
   * their own) gets no page Back, the breadcrumb is their way back.
   */
  hideForLimited?: string;
  /**
   * The label when the page was opened from somewhere else that named itself in `?back=` (a
   * project's Sponsorship Form tab opening a form): Back then returns there, for everyone.
   */
  originLabel?: string;
}

/** The query param a page that opens a record names itself in, so Back returns to it. */
export const BACK_PARAM = 'back';

/**
 * A same-app relative path only: one leading slash, no `//host`, no backslash or control
 * character (WHATWG URL parsing turns `/\evil.test` into another host). Same rule as the
 * review pages' `from` (`isSafeReviewOrigin`).
 */
function safeAppPath(candidate: string | null): string | null {
  return candidate &&
    candidate.startsWith('/') &&
    !candidate.startsWith('//') &&
    !/[\\\x00-\x1f]/.test(candidate)
    ? candidate
    : null;
}

/**
 * A path with this page's list state on the end of it.
 *
 * The list wrote its page, sort, search and filters into the detail URL when the
 * row was clicked, and every link that leads on from here has to carry it: Back,
 * the push after a delete, and the Edit button (the edit screen has a pager of
 * its own, and without the query it walks page 1 of an unfiltered list instead of
 * the page the reader is on). One function, so the hrefs cannot drift apart.
 */
export function useHrefWithListState(path: string, appendListState = true): string {
  const searchParams = useSearchParams();
  // `tab` and `view_*` (a detail grid's own search, filter and sort) are the detail
  // page's own state, not list state, so they must not ride along to the list, the
  // edit screen, or a post-delete redirect.
  const search = useMemo(() => {
    if (!appendListState) return '';
    const params = new URLSearchParams(searchParams.toString());
    params.delete('tab');
    for (const key of [...params.keys()]) if (isDetailViewKey(key)) params.delete(key);
    return params.toString();
  }, [appendListState, searchParams]);
  if (!search) return path;
  // A path that names its own query (a tabbed list's `?tab=dealer`) keeps it first; the list
  // state rides after it.
  const [base, own] = path.split('?');
  return own ? `${base}?${own}&${search}` : `${path}?${search}`;
}

/** The href this page's Back button points at. */
export function useBackToListHref(
  listPath: string,
  appendListState = true,
): string {
  return useHrefWithListState(listPath, appendListState);
}

/**
 * The ONLY thing on a detail page's toolbar action row (D6, S3-01).
 *
 * The list wrote its state into the detail URL when the row was clicked; this
 * hands the same string back, so Back returns to the page the user left rather
 * than to a fresh page 1.
 */
export default function BackToList({
  listPath,
  label,
  appendListState = true,
  className,
  hideForLimited,
  originLabel,
}: BackToListProps) {
  const listHref = useBackToListHref(listPath, appendListState);
  const origin = safeAppPath(useSearchParams().get(BACK_PARAM));
  const href = origin && originLabel ? origin : listHref;

  const button = (
    <Button asChild variant="outline" className={className}>
      <Link href={href}>
        <MoveLeft /> {origin && originLabel ? originLabel : label}
      </Link>
    </Button>
  );
  // Back to where the record was opened from is everyone's way back, a limited user's too.
  if (origin && originLabel) return button;
  return hideForLimited ? <HiddenWhenLimited kind={hideForLimited}>{button}</HiddenWhenLimited> : button;
}

/** Its own component so only the pages that pass `hideForLimited` read the permission hooks. */
function HiddenWhenLimited({ kind, children }: { kind: string; children: ReactNode }) {
  const { limited } = useRequestScope(kind);
  return limited ? null : <>{children}</>;
}
