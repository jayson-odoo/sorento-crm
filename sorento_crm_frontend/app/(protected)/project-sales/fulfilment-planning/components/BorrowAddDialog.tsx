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
import { cn } from '@/lib/utils';
import { fromMinor, toMinor } from '../../_shared/lib/supplyComposition';
import type { BorrowCandidate } from '../../_shared/types/fulfilmentPlanning.types';

const SOURCE_COL = 'w-[170px] min-w-[170px] max-w-[170px]';
const NUMBER_COL = 'w-[88px] min-w-[88px] max-w-[88px]';

/**
 * Borrowing takes exactly one approval: the CS actor who confirms the sales order, with the
 * donor's impact in front of them and a reason nobody can skip (AC-B09, AC-B10). So the
 * reason is mandatory here as well as at the Confirm gate.
 *
 * WHAT THE DONOR LIST NOW STATES, and why (PLAN 13.11). It read "MWH-IB 6990 free, 10
 * committed", and the captain's answer to it was: "before I decide to borrow, I need to know
 * I am not hurting them, so you need to let me know also what's their available, SO qty, SPO
 * and PO qty ... and what's the impact of borrowing. I assume this list is ranked by
 * recommendation, is it?" Free stock nets reserved and confirmed holds only, so on this book
 * it is very nearly raw on-hand - a donor with 6,990 free and 47,000 owed read as the safest
 * one to take from. Each donor is now a row of AutoCount's own columns, and the list arrives
 * RANKED by how little the borrow hurts, with the first row flagged.
 *
 * The ranking is the SERVER's and is never re-sorted here, including as the quantity is
 * typed: a list that reshuffles under the cursor is not a recommendation, and re-deriving the
 * order on the client would be a second implementation of it. It ranks each donor on what
 * meeting THIS line would leave it with (`available_after_need`), which is also what the
 * "After borrow" column shows until a quantity is typed over it.
 *
 * A SAME-AGENT donor takes one more thing (AC-L6, section 1c): the agent whose other order
 * is being drawn on is offered at ANY rank precisely because she can authorise it, so the
 * dialog asks who did. Free text, required only on that donor, and folded into the reason
 * stored beside the quantity - one field to read later, not two.
 *
 * NOT a DataGrid, on the same carve-out `CellStockTable` documents: a fixed matrix of seven
 * named figures inside a dialog, with no column config, sort, resize or pagination to apply
 * to it. Its three obligations are met the same way - the table scrolls inside its own
 * container, cells carry fixed widths on a `w-max` table (never `table-fixed`, which overlaps
 * its columns), and long text truncates with a `title`.
 */
export function BorrowAddDialog({
  lineNo,
  itemCode,
  candidates,
  onDone,
  onAdd,
}: {
  lineNo: number;
  itemCode?: string | null;
  candidates: BorrowCandidate[];
  onDone: () => void;
  onAdd: (candidate: BorrowCandidate, qty: string, reason: string) => void;
}) {
  // The default selection is the first SELECTABLE candidate - an over-cap row (section E
  // rule 5) is shown but disabled, and defaulting onto it would open the dialog with no
  // valid choice made until the planner clicks something themselves.
  const firstSelectable = candidates.find((candidate) => !candidate.over_cap) ?? candidates[0];
  const [selectedKey, setSelectedKey] = React.useState(
    firstSelectable ? candidateKey(firstSelectable) : '',
  );
  const [qty, setQty] = React.useState(openingQty(firstSelectable));
  const [reason, setReason] = React.useState('');
  const [authorisation, setAuthorisation] = React.useState('');

  const selected =
    candidates.find((candidate) => candidateKey(candidate) === selectedKey) ?? firstSelectable;
  const trimmed = reason.trim();
  const authorised = authorisation.trim();
  const needsAuthorisation = Boolean(selected?.same_agent);
  const amount = Number.parseFloat(qty);
  const typed = Number.isFinite(amount) && amount > 0 ? amount : null;
  const valid =
    Boolean(selected) &&
    !selected.over_cap &&
    typed !== null &&
    Boolean(trimmed) &&
    (!needsAuthorisation || Boolean(authorised));

  return (
    <Dialog open onOpenChange={(next) => !next && onDone()}>
      <DialogContent className="max-h-[92vh] w-full max-w-4xl overflow-hidden">
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
              {candidates.length === 0 ? (
                // Rendered rather than hidden, per the CRUD standard: the dialog is opened
                // from a Buy, and "there is nowhere to borrow from" is the answer to why.
                <div
                  data-testid="borrow-donor-empty"
                  className="rounded-lg border border-border px-3 py-2 text-xs text-muted-foreground"
                >
                  No donor holds this item
                </div>
              ) : (
                <div
                  data-testid="borrow-donor-table"
                  className="max-h-[40vh] w-full overflow-x-auto overflow-y-auto overscroll-x-contain rounded-lg border border-border"
                >
                  <table className="w-max border-separate border-spacing-0 text-xs">
                    <thead>
                      <tr>
                        <th scope="col" className={cn(SOURCE_COL, HEAD_CELL)}>
                          Source
                        </th>
                        {NUMERIC_COLUMNS.map((column) => (
                          <th
                            key={column.key}
                            scope="col"
                            className={cn(NUMBER_COL, HEAD_CELL, 'text-end')}
                          >
                            {column.label}
                          </th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {candidates.map((candidate) => {
                        const key = candidateKey(candidate);
                        const code = candidate.warehouse_code;
                        const isGroupBorrow = candidate.rung === 'group_borrow';
                        const donor = isGroupBorrow
                          ? donorSoLabel(candidate)
                          : candidate.source === 'other_project'
                            ? (candidate.donor_project_ref ?? 'Another project')
                            : code;
                        const chosen = key === selectedKey;
                        const disabled = Boolean(candidate.over_cap);
                        return (
                          <tr
                            key={key}
                            data-testid={`borrow-donor-${code}`}
                            className={disabled ? 'opacity-60' : undefined}
                          >
                            <td className={cn(SOURCE_COL, BODY_CELL)}>
                              <label
                                htmlFor={`borrow-${lineNo}-${key}`}
                                className={cn(
                                  'flex items-start gap-2',
                                  disabled ? 'cursor-not-allowed' : 'cursor-pointer',
                                )}
                              >
                                <input
                                  id={`borrow-${lineNo}-${key}`}
                                  type="radio"
                                  name={`borrow-source-${lineNo}`}
                                  className="mt-0.5"
                                  checked={chosen}
                                  disabled={disabled}
                                  onChange={() => {
                                    setSelectedKey(key);
                                    setQty(openingQty(candidate));
                                  }}
                                />
                                <span className="min-w-0">
                                  <span
                                    className="block truncate font-medium"
                                    title={donor}
                                  >
                                    {donor}
                                  </span>
                                  {isGroupBorrow && (
                                    <span
                                      className="block truncate text-muted-foreground"
                                      title={`At ${code}`}
                                    >
                                      {`At ${code}`}
                                    </span>
                                  )}
                                  {!isGroupBorrow && candidate.source === 'other_project' && (
                                    <span
                                      className="block truncate text-muted-foreground"
                                      title={`Held at ${code}`}
                                    >
                                      {`Held at ${code}`}
                                    </span>
                                  )}
                                  <span className="mt-0.5 flex flex-wrap gap-1">
                                    {candidate.recommended && (
                                      <span className="inline-block rounded-sm bg-primary/10 px-1.5 py-0.5 text-[10px] font-medium text-primary">
                                        Recommended
                                      </span>
                                    )}
                                    {candidate.same_agent && (
                                      <span
                                        data-testid={`borrow-same-agent-${code}`}
                                        className="inline-block rounded-sm bg-amber-100 px-1.5 py-0.5 text-[10px] font-medium text-amber-800"
                                        title="This donor shares the line's own sales agent, who can authorise moving her own stock."
                                      >
                                        Same agent
                                      </span>
                                    )}
                                  </span>
                                  {disabled && (
                                    <span
                                      data-testid={`borrow-cap-reason-${code}`}
                                      className="mt-0.5 block text-2xs text-muted-foreground"
                                    >
                                      {candidate.cap_reason ?? 'Outside the cross-group borrow limit.'}
                                    </span>
                                  )}
                                </span>
                              </label>
                            </td>
                            {NUMERIC_COLUMNS.map((column) => {
                              const value = column.of(candidate, typed);
                              // Signed and never clamped: a negative Available IS the hole,
                              // and the colour is what makes it the number the eye lands on.
                              const negative = column.signed && isNegative(value);
                              return (
                                <td key={column.key} className={cn(NUMBER_COL, BODY_CELL)}>
                                  <span
                                    data-testid={`borrow-cell-${column.key}-${code}`}
                                    className={cn(
                                      'block truncate text-end tabular-nums',
                                      value === null && 'text-muted-foreground',
                                      negative && 'text-destructive',
                                    )}
                                    title={value ?? 'Not stated'}
                                  >
                                    {value ?? 'Not stated'}
                                  </span>
                                </td>
                              );
                            })}
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
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

const HEAD_CELL =
  'sticky top-0 z-10 border-b border-e border-border bg-muted px-2 py-1.5 text-start align-bottom font-medium';
const BODY_CELL = 'border-b border-e border-border px-2 py-1.5 align-middle';

/**
 * AutoCount's own columns, in AutoCount's order, closed by what the typed quantity leaves.
 *
 * `Free` is what THIS donor can give - a location's free stock, or a donor project's own hold
 * - because that is the number the borrow is drawn from. The pile's own free figure travels
 * beside it in the payload for reconciliation and is deliberately not a column: two figures
 * both labelled "free" in one row is how a donor list starts lying.
 */
const NUMERIC_COLUMNS: {
  key: string;
  label: string;
  of: (candidate: BorrowCandidate, qty: number | null) => string | null;
  /** May legitimately be negative, and is coloured when it is. */
  signed?: boolean;
}[] = [
  { key: 'on-hand', label: 'On hand', of: (candidate) => candidate.qty_on_hand ?? null },
  { key: 'so', label: 'SO qty', of: (candidate) => candidate.so_qty ?? null },
  { key: 'spo', label: 'SPO qty', of: (candidate) => candidate.spo_qty ?? null },
  {
    key: 'available',
    label: 'Available',
    of: (candidate) => candidate.available_qty ?? null,
    signed: true,
  },
  { key: 'free', label: 'Free', of: (candidate) => candidate.free_qty ?? null },
  {
    key: 'committed',
    label: 'Committed',
    of: (candidate) => candidate.qty_committed ?? candidate.donor_impact?.committed_qty ?? null,
  },
  {
    key: 'after',
    label: 'After borrow',
    // Until a quantity is typed this is the server's own `available_after_need` - what the
    // donor keeps once this line's residual is met, which is the figure it was ranked on.
    // Typing a quantity asks the same question of every donor at that quantity instead.
    of: (candidate, qty) => {
      if (qty === null) return candidate.available_after_need ?? null;
      if (candidate.available_qty === null || candidate.available_qty === undefined) return null;
      return fromMinor(toMinor(candidate.available_qty) - toMinor(qty));
    },
    signed: true,
  },
];

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

function isNegative(value: string | null): boolean {
  return value !== null && Number(value) < 0;
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

/** "SO371334 line 2", the group-borrow donor's own identity - never a bare warehouse code,
 * which two different donor lines at the same location would otherwise share. */
function donorSoLabel(candidate: BorrowCandidate): string {
  const so = candidate.donor_so_number ?? 'An unnamed sales order';
  const line = candidate.donor_line_no !== null && candidate.donor_line_no !== undefined
    ? ` line ${candidate.donor_line_no}`
    : '';
  return `${so}${line}`;
}

function candidateKey(candidate: BorrowCandidate): string {
  return (
    `${candidate.source}-${candidate.warehouse_code}-${candidate.donor_project_ref ?? ''}-` +
    `${candidate.donor_core_line_id ?? ''}`
  );
}
