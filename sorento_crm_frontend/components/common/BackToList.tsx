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
 * The href this page's Back button points at.
 *
 * Deleting a record from its own page has to land where Back would have landed
 * (the page, sort, search and filters the reader left the list on), so both read
 * the same function rather than each rebuilding the string.
 */
export function useBackToListHref(
  listPath: string,
  appendListState = true,
): string {
  const searchParams = useSearchParams();
  const search = appendListState ? searchParams.toString() : '';
  return search ? `${listPath}?${search}` : listPath;
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
