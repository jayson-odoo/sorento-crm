'use client';

import { useMemo } from 'react';
import Link from 'next/link';

import { Checkbox } from '@/components/ui/checkbox';
import { SpecProposalReview } from '@/components/spec-proposals';
import type { SpecProposalKind } from '@/components/spec-proposals';
import { STATUS_PILL_BASE, statusPillClass } from '@/lib/status-pill';
import { readable, readableValue } from '@/lib/spec-readable';
import { cn } from '@/lib/utils';

import type {
  FlyerSpecOutcome,
  FlyerSpecProductGroup,
} from '../services/flyerSpecProposalService';

/**
 * One product's share of a flyer batch.
 *
 * The batch is grouped by PRODUCT and not by specification key, because that is
 * what a reviewer holding the paper is looking at: a card on page 7 is one
 * product saying five things, and a list ordered by key would ask them to jump
 * between three products to judge a single card.
 *
 * The rows themselves are the shared `components/spec-proposals` review, which
 * stays product-blind - this file owns the product identity, the selection
 * translation and nothing else. The shared component's selection is keyed by
 * `spec_key`, because a pasted text has no ids; a stored batch is applied by
 * PROPOSAL ID (L8), and a key is unique per product within a batch, so the
 * translation is exact and lives here rather than in the shared component.
 *
 * Rows that have been through an apply do not come back to the table. There is
 * nothing left to decide about them, and a tick that cannot be applied reads as
 * a broken control - so they move to a plain list underneath carrying what
 * happened to each, which is also the only place a refusal survives a reload.
 */

/**
 * What a BULK apply may tick, which is less than the shared component allows.
 *
 * A conflict is a value a person set, and a tick that replaces one is a decision
 * about that product, made by somebody looking at it (L6/L7). Reviewing this
 * batch is reading a flyer, not reading two hundred products, so the row is
 * shown with what it disagrees with and the per-product Specifications tab is
 * where it is answered. `unchanged` and `suppressed` are refused by the shared
 * component whatever is passed.
 */
const BULK_SELECTABLE_KINDS: readonly SpecProposalKind[] = ['new', 'change'];

/** What each outcome is called on screen. No reason code ever reaches a reader. */
export const OUTCOME_LABEL: Record<FlyerSpecOutcome, string> = {
  applied: 'Applied',
  already_matches: 'Already stored',
  conflict_not_confirmed: 'Not replaced',
  product_spec_bad_value: 'Value refused',
  product_not_found: 'Product not found',
  not_in_batch: 'Not in this batch',
};

/** The shared pill vocabulary, per outcome. Written is green, refused is not. */
const OUTCOME_PILL_KEY: Record<FlyerSpecOutcome, string> = {
  applied: 'done',
  already_matches: 'derived',
  conflict_not_confirmed: 'rejected',
  product_spec_bad_value: 'failed',
  product_not_found: 'failed',
  not_in_batch: 'voided',
};

export function OutcomePill({ outcome }: { outcome: FlyerSpecOutcome }) {
  return (
    <span
      className={cn(
        STATUS_PILL_BASE,
        'shrink-0 normal-case',
        statusPillClass(OUTCOME_PILL_KEY[outcome]),
      )}
      data-flyer-spec-outcome={outcome}
    >
      {OUTCOME_LABEL[outcome]}
    </span>
  );
}

/** "p. 3" / "p. 7, 11". A reviewer is holding the paper. */
function printedOn(pages: number[]): string {
  if (pages.length === 0) return 'Unknown page';
  return `p. ${pages.join(', ')}`;
}

export interface ProductProposalGroupProps {
  group: FlyerSpecProductGroup;
  /** Every ticked id in the batch. Held by the page, so a product cannot own it. */
  selectedIds: ReadonlySet<string>;
  /** The ticked ids OF THIS PRODUCT after the change. The page merges them in. */
  onSelectionChange: (idsForThisProduct: string[]) => void;
  /** True while the batch is being written: rows stay readable, ticks freeze. */
  disabled?: boolean;
}

export function ProductProposalGroup({
  group,
  selectedIds,
  onSelectionChange,
  disabled = false,
}: ProductProposalGroupProps) {
  const pending = useMemo(
    () => group.proposals.filter((row) => row.outcome === null),
    [group.proposals],
  );
  const settled = useMemo(
    () => group.proposals.filter((row) => row.outcome !== null),
    [group.proposals],
  );

  const selectable = useMemo(
    () => pending.filter((row) => BULK_SELECTABLE_KINDS.includes(row.kind)),
    [pending],
  );

  const selectedKeys = useMemo(
    () =>
      pending
        .filter((row) => selectedIds.has(row.id))
        .map((row) => row.spec_key),
    [pending, selectedIds],
  );

  const idByKey = useMemo(
    () => new Map(pending.map((row) => [row.spec_key, row.id])),
    [pending],
  );

  const tickedCount = selectable.filter((row) =>
    selectedIds.has(row.id),
  ).length;
  const allTicked = selectable.length > 0 && tickedCount === selectable.length;
  const someTicked = tickedCount > 0 && !allTicked;

  const toggleAll = (next: boolean) => {
    onSelectionChange(next ? selectable.map((row) => row.id) : []);
  };

  return (
    <section
      className="flex flex-col gap-3 rounded-lg border border-border p-4"
      data-flyer-spec-product={group.product_code}
    >
      <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0">
          <Link
            href={`/master-data-management/products/${group.product_id}`}
            className="font-mono text-sm font-semibold text-foreground hover:underline"
            title={group.product_code}
          >
            {group.product_code}
          </Link>
          <p className="min-w-0 break-words text-sm text-muted-foreground">
            {group.product_name}
          </p>
          <p className="mt-0.5 text-xs text-muted-foreground">
            {printedOn(group.pages)}
          </p>
        </div>

        {/* The select-all for THIS product, and there is no select-all above it:
            a batch can name two hundred products, and one control that ticks
            every change across all of them is a control nobody reviewed. */}
        {selectable.length > 0 && (
          <label className="flex shrink-0 items-center gap-2 text-sm text-muted-foreground">
            <Checkbox
              checked={allTicked ? true : someTicked ? 'indeterminate' : false}
              disabled={disabled}
              onCheckedChange={(value) => toggleAll(!!value)}
              aria-label={`Select every applicable row for ${group.product_code}`}
              data-flyer-spec-select-all={group.product_code}
            />
            <span>
              {tickedCount} of {selectable.length} ticked
            </span>
          </label>
        )}
      </div>

      {pending.length > 0 ? (
        <SpecProposalReview
          proposals={pending}
          selectedKeys={selectedKeys}
          onSelectionChange={(keys) =>
            onSelectionChange(
              keys
                .map((key) => idByKey.get(key))
                .filter((id): id is string => Boolean(id)),
            )
          }
          selectableKinds={BULK_SELECTABLE_KINDS}
          disabled={disabled}
        />
      ) : (
        <p
          className="text-sm text-muted-foreground"
          data-flyer-spec-nothing-pending
        >
          Every row this flyer proposed for this product has been through an
          apply.
        </p>
      )}

      {settled.length > 0 && (
        <div
          className="flex flex-col gap-2"
          data-flyer-spec-settled={group.product_code}
        >
          <p className="text-xs uppercase tracking-wide text-muted-foreground">
            Already decided
          </p>
          <ul className="flex flex-col gap-1.5 text-sm">
            {settled.map((row) => (
              <li key={row.id} className="flex flex-wrap items-center gap-2">
                <span className="font-medium text-foreground">
                  {row.label || readable(row.spec_key)}
                </span>
                <span className="text-muted-foreground">
                  {readableValue(row.value, row.unit ?? undefined)}
                </span>
                <OutcomePill outcome={row.outcome as FlyerSpecOutcome} />
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}
