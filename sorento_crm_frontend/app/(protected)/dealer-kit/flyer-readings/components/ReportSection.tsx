'use client';

import type { ReactNode } from 'react';
import { CheckCircle2, SearchX } from 'lucide-react';

/**
 * One block of the review screen, and the empty state every block owes.
 *
 * Lifted out of `MatchReportSections` when the sizes block grew a mutation of
 * its own and moved into its own file. Shared rather than copied so the two
 * cannot drift into looking like different screens, and so `data-dk-fr-section`
 * stays the one way anything addresses a block.
 */

export function Section({
  id,
  icon,
  title,
  description,
  action,
  children,
}: {
  id: string;
  icon: ReactNode;
  title: string;
  description: ReactNode;
  action?: ReactNode;
  children: ReactNode;
}) {
  return (
    <section className="flex flex-col gap-3" data-dk-fr-section={id}>
      <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
        <div className="flex min-w-0 items-start gap-2">
          <span className="mt-0.5 shrink-0 text-muted-foreground">{icon}</span>
          <div className="min-w-0">
            <h2 className="text-sm font-semibold text-foreground">{title}</h2>
            <p className="mt-0.5 text-sm text-muted-foreground">{description}</p>
          </div>
        </div>
        {/* Wraps under the heading on a phone rather than squeezing it. */}
        {action && <div className="shrink-0">{action}</div>}
      </div>
      {children}
    </section>
  );
}

/** The empty state of a section, always with what it means and what to do next. */
export function Empty({
  tone = 'good',
  title,
  children,
}: {
  tone?: 'good' | 'neutral';
  title: string;
  children: ReactNode;
}) {
  return (
    <div className="py-8 text-center">
      {tone === 'good' ? (
        <CheckCircle2 className="mx-auto size-6 text-green-600" />
      ) : (
        <SearchX className="mx-auto size-6 text-muted-foreground" />
      )}
      <p className="mt-3 text-sm font-medium text-foreground">{title}</p>
      <p className="mx-auto mt-1 max-w-md text-sm text-muted-foreground">{children}</p>
    </div>
  );
}

/** A millimetre figure without a pointless `.0`. */
export function mm(value: number | null): string {
  if (value === null || Number.isNaN(value)) return '';
  return Number.isInteger(value) ? String(value) : String(Number(value.toFixed(1)));
}

/** `1700 x 800 x 590 mm`, or nothing at all when the row holds nothing. */
export function size(
  length: number | null,
  width: number | null,
  height: number | null,
): string | null {
  if (length === null && width === null && height === null) return null;
  return `${mm(length)} x ${mm(width)} x ${mm(height)} mm`;
}

/** "p. 3" / "p. 3, 11". A reviewer is holding the paper. */
export function printedOn(pages: number[]): string {
  if (pages.length === 0) return 'Unknown page';
  return `p. ${pages.join(', ')}`;
}
