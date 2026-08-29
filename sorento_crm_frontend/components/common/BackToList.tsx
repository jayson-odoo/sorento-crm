'use client';

import Link from 'next/link';
import { useSearchParams } from 'next/navigation';
import { MoveLeft } from 'lucide-react';
import { Button } from '@/components/ui/button';

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
  const search = appendListState ? searchParams.toString() : '';
  return search ? `${path}?${search}` : path;
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
}: BackToListProps) {
  const href = useBackToListHref(listPath, appendListState);

  return (
    <Button asChild variant="outline" className={className}>
      <Link href={href}>
        <MoveLeft /> {label}
      </Link>
    </Button>
  );
}
