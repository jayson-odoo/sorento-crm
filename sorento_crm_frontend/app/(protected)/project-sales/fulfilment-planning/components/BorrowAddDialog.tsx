'use client';

import * as React from 'react';
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { fromMinor, toMinor } from '../../_shared/lib/supplyComposition';
import { CellStockTable, type DonorLocationRow } from './CellStockTable';
import type { BorrowCandidate } from '../../_shared/types/fulfilmentPlanning.types';

/**
 * Borrowing takes exactly one approval: the CS actor who confirms the sales order, with the
 * donor's impact in front of them and a reason nobody can skip (AC-B09, AC-B10). So the
 * reason is mandatory here as well as at the Confirm gate.
 *
 * THE SOURCE IS THE GRID LOCATION TABLE (S4, `PLAN-local-supplier-oi-routing.md`,
 * AC-1.4/AC-1.5): the same `CellStockTable` the Grid view renders, fed by each candidate's
 * own `location` (`BoardCellLocation`), with a radio in the Location cell instead of the
 * List view's read-only row and `Recommended` / `Same agent` badges beside the code. Row
 * expansion mounts the same `StockDocumentsPanel` ledger, `This line` marking the line this
 * dialog was opened for. Group subtotal rows are hidden (`showGroupSubtotal={false}`): a
 * donor list is not a group.
 *
 * This replaces the dialog's own seven-column table (`On hand · SO qty · SPO qty ·
 * Available · Free · Committed · After borrow`), which repeated arithmetic
 * `CellStockTable` already carries and answered nothing about which sales orders sit on a
 * source - the very question the Grid view's ledger exists to answer. Candidates carrying
 * no `location` yet (a server that has not wired S4) render as though nothing were free
 * there, same as an empty stock position.
 *
 * The RANKING is unchanged and is still the SERVER's: `(same_agent desc, required_date desc,
 * same_group desc, same_warehouse desc)` (R4, R19) - her own agent first, then the order that
 * can wait longest, then the same ownership group, then the asker's own warehouse. This
 * dialog never re-sorts it, including as the quantity is typed.
 *
 * A SAME-AGENT donor takes one more thing (AC-L6, section 1c): the agent whose other order
 * is being drawn on is offered at ANY rank precisely because she can authorise it, so the
 * dialog asks who did. Free text, required only on that donor, and folded into the reason
 * stored beside the quantity - one field to read later, not two.
 */
export function BorrowAddDialog({
  lineNo,
  itemCode,
  lineId,
  candidates,
  onDone,
  onAdd,
}: {
  lineNo: number;
  itemCode?: string | null;
  /** The mirror line this borrow is FOR, so its own rows are marked `This line` in the
   * ledger a source row expands into. Absent on a caller with no mirror line yet. */
  lineId?: string | null;
  candidates: BorrowCandidate[];
  onDone: () => void;
  onAdd: (candidate: BorrowCandidate, qty: string, reason: string) => void;
}) {
  // Every candidate is selectable since v7.1 (R5): the cross-group cap that used to show a
  // row disabled and unselectable is gone, so the opening selection is simply the first of
  // the ranked list - which is also the recommended one.
  const first = candidates[0];
  // S4/review B2: keyed by CANDIDATE, not by warehouse - two donors can share one bin (a
  // same-agent Borrow off two different sales-order lines), and `warehouse_id` alone would
  // make the second row's radio silently select the first.
  const [selectedKey, setSelectedKey] = React.useState(first ? candidateKey(first) : '');
  const [qty, setQty] = React.useState(openingQty(first));
  const [reason, setReason] = React.useState('');
  const [authorisation, setAuthorisation] = React.useState('');

  const selected = candidates.find((candidate) => candidateKey(candidate) === selectedKey) ?? first;
  const trimmed = reason.trim();
  const authorised = authorisation.trim();
  const needsAuthorisation = Boolean(selected?.same_agent);
  const amount = Number.parseFloat(qty);
  const typed = Number.isFinite(amount) && amount > 0 ? amount : null;

  // S4/review S3: `rowKey`/`label` are CellStockTable's own opt-in fields for a donor
  // picker - every OTHER caller (the Grid Location table) sets neither and keys/labels
  // itself off the location alone, unchanged.
  const locations = React.useMemo<DonorLocationRow[]>(
    () =>
      candidates
        .filter((c) => c.location)
        .map((c) => ({
          ...(c.location as NonNullable<BorrowCandidate['location']>),
          rowKey: candidateKey(c),
          label: donorLabel(c),
        })),
    [candidates],
  );
  // Every candidate lacks a `location` (a server that has not wired S4) reads the same as
  // no candidates at all: the DIALOG's own empty state, never `CellStockTable`'s "No stock
  // position for this cell" - that message is about a CELL with several products, and is
  // simply the wrong sentence for a donor list with nothing to offer.
  const hasDonors = locations.length > 0;
  const valid =
    hasDonors &&
    Boolean(selected) &&
    typed !== null &&
    Boolean(trimmed) &&
    (!needsAuthorisation || Boolean(authorised));

  const badges = React.useMemo(() => {
    const map: Record<string, ('Recommended' | 'Same agent')[]> = {};
    for (const candidate of candidates) {
      const tags: ('Recommended' | 'Same agent')[] = [];
      if (candidate.recommended) tags.push('Recommended');
      if (candidate.same_agent) tags.push('Same agent');
      if (tags.length > 0) map[candidateKey(candidate)] = tags;
    }
    return map;
  }, [candidates]);

  return (
    <Dialog open onOpenChange={(next) => !next && onDone()}>
      <DialogContent className="max-h-[92vh] w-full max-w-5xl overflow-hidden">
        <DialogHeader>
          <DialogTitle>Borrow for line {lineNo}</DialogTitle>
          <DialogDescription>{itemCode ?? 'This item'}</DialogDescription>
        </DialogHeader>

        <form
          onSubmit={(event) => {
            event.preventDefault();
            if (!valid || !selected) return;
            onAdd(selected, qty.trim(), storedReason(selected, authorised, trimmed));
            onDone();
          }}
        >
          <DialogBody className="max-h-[60vh] space-y-4 overflow-y-auto">
            <fieldset className="space-y-2">
              <legend className="mb-1.5 text-sm font-medium">Source</legend>
              {!hasDonors ? (
                // Rendered rather than hidden, per the CRUD standard: the dialog is opened
                // from a Buy, and "there is nowhere to borrow from" is the answer to why.
                // Review S3: this is the dialog's OWN empty state, shown whether there are
                // no candidates at all or every candidate lacks a `location` - never
                // `CellStockTable`'s own "No stock position for this cell", which answers a
                // different question (a cell holding several products, not a donor list).
                <div
                  data-testid="borrow-donor-empty"
                  className="rounded-lg border border-border px-3 py-2 text-xs text-muted-foreground"
                >
                  No donor holds this item
                </div>
              ) : (
                <div
                  data-testid="borrow-donor-table"
                  className="max-h-[40vh] w-full overflow-x-auto overflow-y-auto overscroll-x-contain"
                >
                  <CellStockTable
                    locations={locations}
                    selectable={{
                      value: selectedKey,
                      onChange: (key) => {
                        const next = candidates.find(
                          (candidate) => candidateKey(candidate) === key,
                        );
                        if (!next) return;
                        setSelectedKey(key);
                        setQty(openingQty(next));
                        // The authorisation names ONE agent and belongs to the donor it was
                        // typed for. Carrying it onto the next donor would file somebody
                        // else's approval against an order they never agreed to give stock
                        // from.
                        setAuthorisation('');
                      },
                    }}
                    badges={badges}
                    lineIds={lineId ? [lineId] : []}
                    showGroupSubtotal={false}
                  />
                </div>
              )}
            </fieldset>

            <div className="space-y-1.5">
              <Label htmlFor={`borrow-qty-${lineNo}`}>Quantity</Label>
              <Input
                id={`borrow-qty-${lineNo}`}
                type="number"
                min="0"
                step="any"
                value={qty}
                onChange={(event) => setQty(event.target.value)}
                className="h-9 w-40 tabular-nums"
              />
            </div>

            <BorrowImpact candidate={selected} qty={typed} />

            {needsAuthorisation && (
              <div className="space-y-1.5">
                <Label htmlFor={`borrow-authorisation-${lineNo}`}>
                  {authorisationLabel(selected)} <span className="text-destructive">*</span>
                </Label>
                <Input
                  id={`borrow-authorisation-${lineNo}`}
                  value={authorisation}
                  onChange={(event) => setAuthorisation(event.target.value)}
                  placeholder="When, and how"
                  className="h-9"
                />
              </div>
            )}

            <div className="space-y-1.5">
              <Label htmlFor={`borrow-reason-${lineNo}`}>
                Reason <span className="text-destructive">*</span>
              </Label>
              <Textarea
                id={`borrow-reason-${lineNo}`}
                value={reason}
                onChange={(event) => setReason(event.target.value)}
                rows={3}
                placeholder="In your own words"
              />
            </div>
          </DialogBody>

          <DialogFooter className="flex-col gap-2 sm:flex-row sm:justify-end">
            <Button type="button" variant="outline" onClick={onDone}>
              Cancel
            </Button>
            <Button type="submit" disabled={!valid}>
              Add the borrow
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

/**
 * What this quantity does to the chosen donor, in one line, updated as it is typed.
 *
 * Always rendered, including before a quantity exists: the section is where the answer to
 * "am I hurting them" lives, and a section that appears only once it is bad reads as an
 * error message rather than as the arithmetic it is.
 *
 * A donor pushed below zero availability is the ONLY case that raises anything back, so it is
 * the only case that says so (PLAN 13.11). A borrow a donor can afford is a plain transfer.
 */
function BorrowImpact({
  candidate,
  qty,
}: {
  candidate: BorrowCandidate | undefined;
  qty: number | null;
}) {
  if (!candidate) {
    return (
      <p data-testid="borrow-impact" className="text-xs text-muted-foreground">
        No donor chosen yet
      </p>
    );
  }
  if (qty === null) {
    return (
      <p data-testid="borrow-impact" className="text-xs text-muted-foreground">
        No quantity yet
      </p>
    );
  }

  const available = candidate.available_qty ?? null;
  if (available === null) {
    return (
      <p data-testid="borrow-impact" className="text-xs text-muted-foreground">
        {`After borrowing ${fromMinor(toMinor(qty))}: this donor's availability is not stated.`}
      </p>
    );
  }

  const after = toMinor(available) - toMinor(qty);
  const freeAfter = Math.max(toMinor(candidate.free_qty) - toMinor(qty), 0);
  if (after < 0) {
    return (
      <p data-testid="borrow-impact" className="text-xs font-medium text-destructive">
        {`After borrowing ${fromMinor(toMinor(qty))}: ${candidate.warehouse_code} goes short by ` +
          `${fromMinor(-after)} - an Order Inquiry will be raised for ` +
          `${candidate.warehouse_code} on confirm.`}
      </p>
    );
  }
  return (
    <p data-testid="borrow-impact" className="text-xs text-muted-foreground">
      {`After borrowing ${fromMinor(toMinor(qty))}: available ${fromMinor(after)}, free ` +
        `${fromMinor(freeAfter)}.`}
    </p>
  );
}

/**
 * What the box opens on: what this line still has to cover, capped at what the donor has.
 *
 * NOT the donor's whole free stock, which is what it used to be. The list is ranked on meeting
 * the line's residual (PLAN 13.11), so opening on "take all 11,000 of it" would contradict the
 * recommendation it sits under and would hide the default `After borrow` figure behind a typed
 * quantity nobody chose. A candidate the server stated no need for falls back to its free
 * quantity, which is the old behaviour and the only honest guess left.
 */
function openingQty(candidate: BorrowCandidate | undefined): string {
  if (!candidate) return '';
  const need = candidate.need_qty ?? null;
  if (need === null || toMinor(need) <= 0) return candidate.free_qty;
  return fromMinor(Math.min(toMinor(need), toMinor(candidate.free_qty)));
}

/**
 * The authorisation field's own label, naming the agent when the donor states one (AC-L6).
 * "Authorised by agent JEREMY" is a person CS can point at; "Authorised" alone is not.
 */
function authorisationLabel(candidate: BorrowCandidate | undefined): string {
  const agent = candidate?.donor_agent_code;
  return agent ? `Authorised by agent ${agent}` : 'Authorised by the sales agent';
}

/**
 * What is stored beside the quantity: the authorisation first, then the planner's own words.
 * ONE field, because `so_line_allocations.reason` is one column and two half-sentences in two
 * places is how a reason stops being readable.
 */
function storedReason(
  candidate: BorrowCandidate,
  authorised: string,
  reason: string,
): string {
  if (!candidate.same_agent || !authorised) return reason;
  return `${authorisationLabel(candidate)}: ${authorised}. ${reason}`;
}

/**
 * A stable identity for ONE candidate, not for the warehouse it names (S4/review B2).
 * `warehouse_id` alone collided the moment two donor lines shared a bin - a same-agent
 * Borrow off two different sales-order lines at MWH-BB is two rows, and without
 * `donor_core_line_id` in the key the second row's radio silently selected the first.
 */
function candidateKey(candidate: BorrowCandidate): string {
  return [
    candidate.warehouse_id ?? '',
    candidate.source,
    candidate.donor_core_line_id ?? '',
    candidate.donor_project_ref ?? '',
  ].join('|');
}

/**
 * The donor's own identity, shown under the location code (S4/review B2) - never a bare
 * warehouse code, which two donor lines at the same location would otherwise share.
 * `undefined` for a plain free-stock donor: the code alone already fully identifies it.
 */
function donorLabel(candidate: BorrowCandidate): string | undefined {
  if (candidate.rung === 'group_borrow') {
    return donorSoLabel(candidate);
  }
  if (candidate.source === 'other_project') {
    return candidate.donor_project_ref ?? 'Another project';
  }
  return undefined;
}

/** "SO371334 line 2" - a group-borrow donor's own identity, never a bare warehouse code. */
function donorSoLabel(candidate: BorrowCandidate): string {
  const so = candidate.donor_so_number ?? 'An unnamed sales order';
  const line =
    candidate.donor_line_no !== null && candidate.donor_line_no !== undefined
      ? ` line ${candidate.donor_line_no}`
      : '';
  return `${so}${line}`;
}
