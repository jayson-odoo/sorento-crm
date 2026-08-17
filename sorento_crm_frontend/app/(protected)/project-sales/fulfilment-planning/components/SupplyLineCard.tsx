'use client';

import * as React from 'react';
import { AlertTriangle, Plus, Trash2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { STATUS_PILL_BASE, statusPillClass } from '@/lib/status-pill';
import { formatDateInMalaysia } from '@/lib/helpers';
import type {
  BorrowCandidate,
  SupplyComponent,
  SupplyLine,
  SupplySpoRef,
} from '../../_shared/types/fulfilmentPlanning.types';
import {
  fromMinor,
  lineBalance,
  lineBlockers,
  toMinor,
  type DraftBorrow,
  type DraftLine,
} from '../../_shared/lib/supplyComposition';
import { BorrowAddDialog } from './BorrowAddDialog';

/**
 * One line's composition (journey steps 1 and 2).
 *
 * The read view and the edit view are the same layout: a confirmed line shows the frozen
 * quantity where the input was, in the same order, under the same headings. Nothing moves,
 * appears or disappears when a decision lands, because the read view is what taught the
 * reader where things are.
 *
 * Every section renders whatever the answer is (AC-G02). No eligible stock, no incoming by
 * the required date, no later incoming, no borrow candidate, no reorder level and no
 * classification each state that in place; a section that disappears reads as a screen
 * that has not finished loading.
 */
export function SupplyLineCard({
  line,
  draft,
  frozen,
  onChange,
}: {
  line: SupplyLine;
  draft: DraftLine;
  /** The composition is a decision that stands: it is shown, not edited. */
  frozen: boolean;
  onChange: (next: DraftLine) => void;
}) {
  const [adding, setAdding] = React.useState(false);

  const frozenComponents = line.frozen?.components ?? [];
  const balance = lineBalance(draft);
  const blockers = frozen ? [] : lineBlockers(draft);
  const uom = line.uom ? ` ${line.uom}` : '';
  const openQty = frozen ? (line.frozen?.open_qty ?? line.open_qty) : line.open_qty;

  const frozenOf = (kind: SupplyComponent['kind']) =>
    frozenComponents.filter((component) => component.kind === kind);

  const setBorrow = (borrow: DraftBorrow[]) => onChange({ ...draft, borrow });

  return (
    <article className="rounded-lg border border-border">
      <header className="flex flex-col gap-1 border-b border-border px-3 py-2.5 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0">
          <div className="truncate text-sm font-medium">
            {`Line ${line.line_no}${line.item_code ? ` · ${line.item_code}` : ''}`}
          </div>
          <div className="truncate text-sm text-muted-foreground" title={line.description ?? ''}>
            {line.description || 'No description'}
          </div>
        </div>
        <div className="shrink-0 text-sm tabular-nums sm:text-end">
          <span className="font-medium">{`${openQty}${uom}`}</span>
          <span className="text-muted-foreground"> open</span>
        </div>
      </header>

      <div className="grid grid-cols-2 gap-3 border-b border-border px-3 py-2.5 sm:grid-cols-3">
        <Fact label="Required">
          {line.required_date ? (
            <span className="tabular-nums">{formatDateInMalaysia(line.required_date)}</span>
          ) : (
            <Muted>No date</Muted>
          )}
        </Fact>
        <Fact label="Fulfil from">
          {line.fulfilment_location ? (
            <span>{line.fulfilment_location}</span>
          ) : (
            <Muted>Not set</Muted>
          )}
        </Fact>
        <Fact label="Retail classification">
          {line.classification_unavailable ? (
            <span
              className={`${STATUS_PILL_BASE} normal-case ${statusPillClass('unknown')}`}
              title="Retail classification unavailable"
            >
              Unavailable
            </span>
          ) : line.is_dealer_hot_selling ? (
            <span
              className={`${STATUS_PILL_BASE} normal-case ${statusPillClass('pending')}`}
              title="Hot selling at a dealer location"
            >
              Hot selling
            </span>
          ) : (
            <Muted>Not hot selling</Muted>
          )}
        </Fact>
      </div>

      {/* Reserve evidence: the pool, its level and the cap the two produce. Rendered on
          every line, so "no reorder level is set" is stated rather than left blank. */}
      <div className="border-b border-border px-3 py-2.5 text-sm">
        <div className="text-2xs uppercase tracking-wide text-muted-foreground">
          Reserve pool
        </div>
        {line.pool_location ? (
          <p className="break-words">
            {line.pool_location}
            {line.pool_reorder_level
              ? `, reorder level ${line.pool_reorder_level}`
              : ', no reorder level set'}
            {line.is_dealer_hot_selling
              ? `. Dealer stock is out; the pool draw stops at ${line.pool_cap ?? '0'}.`
              : '.'}
          </p>
        ) : (
          <Muted>No pool is configured for this location.</Muted>
        )}
      </div>

      {line.is_discontinued && (
        <div className="flex items-start gap-2 border-b border-border bg-destructive/5 px-3 py-2.5 text-sm">
          <AlertTriangle className="mt-0.5 size-4 shrink-0 text-destructive" aria-hidden />
          <span>This product is discontinued. Buying it takes a reason.</span>
        </div>
      )}

      {/* Components, in the order the engine proposes them (plan 3.2). */}
      <div className="divide-y divide-border">
        <Row label="Incoming by the required date">
          {frozen ? (
            <FrozenComponents components={frozenOf('timely_spo')} uom={uom} />
          ) : line.timely_spo.length === 0 ? (
            <Muted>No incoming arrives by the required date.</Muted>
          ) : (
            <div className="space-y-1">
              <div className="text-sm tabular-nums">{`${draft.timely_spo_qty}${uom}`}</div>
              {line.components
                .filter((component) => component.kind === 'timely_spo')
                .map((component, index) => (
                  <Reason key={`timely-${index}`}>{component.reason}</Reason>
                ))}
              <SpoList refs={line.timely_spo} />
            </div>
          )}
        </Row>

        <Row label="Reserve">
          {frozen ? (
            <FrozenComponents components={frozenOf('reserve')} uom={uom} />
          ) : draft.reserve.length === 0 ? (
            <Muted>
              {`No eligible free stock to reserve${
                line.fulfilment_location ? ` at ${line.fulfilment_location}` : ''
              }.`}
            </Muted>
          ) : (
            <div className="space-y-2">
              {draft.reserve.map((row, index) => (
                <div key={row.key} className="space-y-1">
                  <div className="flex items-center gap-2">
                    <Input
                      type="number"
                      min="0"
                      step="any"
                      value={row.qty}
                      aria-label={`Reserve at ${row.location ?? 'the fulfilment location'} on line ${line.line_no}`}
                      onChange={(event) => {
                        const next = [...draft.reserve];
                        next[index] = { ...row, qty: event.target.value };
                        onChange({ ...draft, reserve: next });
                      }}
                      className="h-8 w-28 tabular-nums"
                    />
                    <span className="text-sm text-muted-foreground">
                      {row.location ?? 'Location not set'}
                    </span>
                  </div>
                  <Reason>{row.reason}</Reason>
                </div>
              ))}
            </div>
          )}
        </Row>

        <Row label="Borrow">
          {frozen ? (
            <FrozenComponents components={frozenOf('borrow')} uom={uom} />
          ) : (
            <div className="space-y-3">
              {draft.borrow.length === 0 ? (
                <Muted>Nothing is borrowed on this line.</Muted>
              ) : (
                draft.borrow.map((row, index) => (
                  <div key={row.key} className="space-y-1.5">
                    <div className="flex items-center gap-2">
                      <Input
                        type="number"
                        min="0"
                        step="any"
                        value={row.qty}
                        aria-label={`Borrow from ${row.donor_project_ref ?? row.warehouse_code} on line ${line.line_no}`}
                        onChange={(event) => {
                          const next = [...draft.borrow];
                          next[index] = { ...row, qty: event.target.value };
                          setBorrow(next);
                        }}
                        className="h-8 w-28 tabular-nums"
                      />
                      <span className="min-w-0 truncate text-sm text-muted-foreground">
                        {row.donor_project_ref
                          ? `${row.donor_project_ref} at ${row.warehouse_code}`
                          : row.warehouse_code}
                      </span>
                      <Button
                        type="button"
                        mode="icon"
                        variant="dim"
                        aria-label={`Remove the borrow from ${row.donor_project_ref ?? row.warehouse_code} on line ${line.line_no}`}
                        onClick={() =>
                          setBorrow(draft.borrow.filter((entry) => entry.key !== row.key))
                        }
                      >
                        <Trash2 />
                      </Button>
                    </div>
                    <p className="text-sm text-muted-foreground break-words">
                      {`${row.donor_impact.free_before} free before, ${row.donor_impact.free_after_full_borrow} after taking all of it, ${row.donor_impact.committed_qty} committed.`}
                    </p>
                    <div className="space-y-1">
                      <label
                        className="block text-2xs uppercase tracking-wide text-muted-foreground"
                        htmlFor={`borrow-reason-${line.project_line_id}-${row.key}`}
                      >
                        Reason <span className="text-destructive">*</span>
                      </label>
                      <Textarea
                        id={`borrow-reason-${line.project_line_id}-${row.key}`}
                        value={row.reason}
                        rows={2}
                        placeholder="In your own words"
                        onChange={(event) => {
                          const next = [...draft.borrow];
                          next[index] = { ...row, reason: event.target.value };
                          setBorrow(next);
                        }}
                      />
                    </div>
                  </div>
                ))
              )}

              {line.borrow_candidates.length === 0 ? (
                <Muted>No other location or project holds free stock of this item.</Muted>
              ) : (
                <Button type="button" variant="outline" size="sm" onClick={() => setAdding(true)}>
                  <Plus className="size-4" aria-hidden />
                  Add a borrow
                </Button>
              )}
            </div>
          )}
        </Row>

        <Row label="Buy">
          {frozen ? (
            <FrozenComponents components={frozenOf('buy')} uom={uom} />
          ) : (
            <div className="space-y-2">
              <div className="flex items-center gap-2">
                <Input
                  type="number"
                  min="0"
                  step="any"
                  value={draft.buy_qty}
                  aria-label={`Buy on line ${line.line_no}`}
                  onChange={(event) => onChange({ ...draft, buy_qty: event.target.value })}
                  className="h-8 w-28 tabular-nums"
                />
                <span className="text-sm text-muted-foreground">To purchase</span>
              </div>
              {line.components
                .filter((component) => component.kind === 'buy')
                .map((component, index) => (
                  <Reason key={`buy-${index}`}>{component.reason}</Reason>
                ))}
              {line.is_discontinued && (
                <div className="space-y-1">
                  <label
                    className="block text-2xs uppercase tracking-wide text-muted-foreground"
                    htmlFor={`buy-reason-${line.project_line_id}`}
                  >
                    Reason <span className="text-destructive">*</span>
                  </label>
                  <Textarea
                    id={`buy-reason-${line.project_line_id}`}
                    value={draft.buy_reason}
                    rows={2}
                    placeholder="In your own words"
                    onChange={(event) => onChange({ ...draft, buy_reason: event.target.value })}
                  />
                </div>
              )}
            </div>
          )}
        </Row>

        <Row label="Later incoming">
          {line.advisory_spo.length === 0 ? (
            <Muted>No later incoming for this item at this location.</Muted>
          ) : (
            <div className="space-y-1">
              <SpoList refs={line.advisory_spo} />
              <Muted>Advisory: it arrives after the required date and covers nothing.</Muted>
            </div>
          )}
        </Row>
      </div>

      {/* The balance CS is editing against, and what stops the Confirm. */}
      <footer className="space-y-1.5 border-t border-border px-3 py-2.5">
        <div className="text-sm tabular-nums break-words">
          {frozen
            ? `${openQty} open = ${frozenTotal(frozenComponents)} composed`
            : `${draft.open_qty} open = ${fromMinor(balance.timelyMinor)} incoming + ${fromMinor(
                balance.reserveMinor,
              )} reserve + ${fromMinor(balance.borrowMinor)} borrow + ${fromMinor(
                balance.buyMinor,
              )} buy`}
        </div>
        {!frozen && blockers.length > 0 && (
          <ul className="space-y-0.5">
            {blockers.map((blocker) => (
              <li key={blocker} className="text-sm text-destructive break-words">
                {blocker}
              </li>
            ))}
          </ul>
        )}
      </footer>

      {adding && (
        <BorrowAddDialog
          lineNo={line.line_no}
          itemCode={line.item_code}
          candidates={line.borrow_candidates}
          onDone={() => setAdding(false)}
          onAdd={(candidate: BorrowCandidate, qty, reason) =>
            setBorrow([
              ...draft.borrow,
              {
                key: `borrow-${line.project_line_id}-${candidate.warehouse_code}-${draft.borrow.length}`,
                source: candidate.source,
                warehouse_code: candidate.warehouse_code,
                warehouse_id: candidate.warehouse_id,
                donor_project_ref: candidate.donor_project_ref,
                donor_project_id: candidate.donor_project_id,
                qty,
                reason,
                donor_impact: candidate.donor_impact,
              },
            ])
          }
        />
      )}
    </article>
  );
}

function frozenTotal(components: SupplyComponent[]): string {
  return fromMinor(components.reduce((total, component) => total + toMinor(component.qty), 0));
}

function FrozenComponents({
  components,
  uom,
}: {
  components: SupplyComponent[];
  uom: string;
}) {
  if (components.length === 0) return <Muted>None</Muted>;
  return (
    <div className="space-y-1.5">
      {components.map((component, index) => (
        <div key={`${component.kind}-${index}`} className="space-y-0.5">
          <div className="text-sm tabular-nums">
            {`${component.qty}${uom}`}
            {component.source_location ? (
              <span className="text-muted-foreground">{` at ${component.source_location}`}</span>
            ) : null}
            {component.donor_project_ref ? (
              <span className="text-muted-foreground">{` for ${component.donor_project_ref}`}</span>
            ) : null}
          </div>
          <Reason>{component.reason}</Reason>
          {component.cs_reason ? (
            <p className="text-sm break-words">{component.cs_reason}</p>
          ) : null}
        </div>
      ))}
    </div>
  );
}

function SpoList({ refs }: { refs: SupplySpoRef[] }) {
  return (
    <ul className="space-y-0.5">
      {refs.map((entry) => (
        <li key={`${entry.spo_number}-${entry.arrival_date ?? ''}`} className="text-sm">
          <span className="tabular-nums">{entry.spo_number}</span>
          <span className="text-muted-foreground">
            {` · ${entry.qty}${entry.arrival_date ? ` · ${formatDateInMalaysia(entry.arrival_date)}` : ''}`}
          </span>
        </li>
      ))}
    </ul>
  );
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="grid gap-1 px-3 py-2.5 sm:grid-cols-[9.5rem_minmax(0,1fr)] sm:gap-3">
      <div className="text-2xs uppercase tracking-wide text-muted-foreground sm:pt-1.5">
        {label}
      </div>
      <div className="min-w-0">{children}</div>
    </div>
  );
}

function Fact({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="min-w-0">
      <div className="truncate text-2xs uppercase tracking-wide text-muted-foreground">
        {label}
      </div>
      <div className="truncate text-sm">{children}</div>
    </div>
  );
}

function Reason({ children }: { children: React.ReactNode }) {
  return <p className="text-sm text-muted-foreground break-words">{children}</p>;
}

/** Block, not inline: two empty states in one section must not run into one sentence. */
function Muted({ children }: { children: React.ReactNode }) {
  return <span className="block text-sm text-muted-foreground">{children}</span>;
}
