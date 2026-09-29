'use client';

import * as React from 'react';
import { ChevronDown } from 'lucide-react';
import { cn } from '@/lib/utils';
import { formatDateInMalaysia } from '@/lib/helpers';
import { phaseRowLabel } from '../lib/scheduleTotals';
import { firstEditableCell, isDisplayed } from './DeliveryScheduleMatrix';
import type { ScheduleGridController } from './DeliveryScheduleMatrix';
import { DeliveryScheduleFlagCell } from './DeliveryScheduleFlagCell';

/**
 * The same grid on a phone, turned ninety degrees.
 *
 * A 38-column matrix cannot be read at 375px and a horizontal scroller there means dragging
 * across two screens per row to find one number. The unit of work on this screen is a COLUMN
 * (reconciliation is per column, corrections are per column), so on a phone each column
 * becomes a card carrying its two totals and the same Flag pill the matrix row carries (its
 * popover holds the fix and the Dismiss), and its phase quantities open underneath. Only the
 * open card renders inputs, which also keeps a 500-cell schedule from mounting 500 fields on a
 * phone.
 */
export function DeliveryScheduleColumnCards({
  controller,
}: {
  controller: ScheduleGridController;
}) {
  const [openKey, setOpenKey] = React.useState<string | null>(null);
  const { columns, phaseGroups, focusRequest } = controller;
  const rootRef = React.useRef<HTMLDivElement>(null);

  /**
   * "Fix the quantities" on a phone has to open the card first: a closed card mounts no
   * fields at all, so there is nothing to focus until it is open. Two effects, because the
   * field only exists in the commit AFTER the one that opened the card.
   *
   * Only when this view is the one on screen. Opening a card is a visible change, and at
   * desktop width the matrix is answering the same request.
   */
  React.useEffect(() => {
    if (focusRequest && isDisplayed(rootRef.current)) setOpenKey(focusRequest.key);
  }, [focusRequest]);

  // The nonce already answered, so opening the same card again by hand later does not
  // silently grab the cursor a second time.
  const answered = React.useRef(0);

  React.useEffect(() => {
    if (!focusRequest || openKey !== focusRequest.key) return;
    if (answered.current === focusRequest.nonce) return;
    answered.current = focusRequest.nonce;
    const cell = firstEditableCell(rootRef.current, focusRequest.key);
    if (!cell) return;
    cell.focus();
    // jsdom implements no scrollIntoView, hence the optional call.
    cell.scrollIntoView?.({ behavior: 'smooth', block: 'nearest' });
  }, [focusRequest, openKey]);

  return (
    <div ref={rootRef} data-testid="schedule-columns-mobile" className="space-y-2">
      {columns.map((column) => {
        const open = openKey === column.key;
        return (
          <div
            key={column.key}
            // The same registration the matrix does, so a jump to this column reaches it on
            // a phone too: the matrix that owns the other refs is not laid out at 375px.
            ref={(node) => controller.registerColumnRef(column.key, node)}
            className={cn(
              'rounded-lg border',
              column.reconciled ? 'border-border' : 'border-destructive/40 bg-destructive/5',
            )}
          >
            <div className="flex items-start gap-2 px-3 py-2.5">
              <button
                type="button"
                onClick={() => setOpenKey(open ? null : column.key)}
                aria-expanded={open}
                className="flex min-w-0 flex-1 items-start gap-2 text-start"
              >
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-sm font-medium">
                    {column.productCode ?? 'Not identified'}
                  </span>
                  {column.customerCode && (
                    <span className="mt-0.5 block break-all text-xs text-muted-foreground">
                      {column.customerCode}
                    </span>
                  )}
                  <span className="mt-1 grid grid-cols-2 gap-2 text-xs">
                    <NumberCell
                      label="Schedule"
                      value={column.ourTotal}
                      emphasise
                      wrong={column.blockers.some((b) => b.code === 'reported_mismatch')}
                    />
                    <NumberCell
                      label="PO"
                      value={column.poQty}
                      missing="Not on the PO"
                      wrong={column.blockers.some(
                        (b) => b.code === 'po_mismatch' || b.code === 'not_on_po',
                      )}
                    />
                  </span>
                </span>
                <ChevronDown
                  className={cn('mt-1 size-4 shrink-0 transition-transform', open && 'rotate-180')}
                  aria-hidden
                />
              </button>
              <div className="shrink-0">
                <DeliveryScheduleFlagCell
                  column={column}
                  actions={controller.flagActions}
                  idPrefix="schedule-phone"
                />
              </div>
            </div>

            {open && (
              <div className="space-y-3 border-t border-border px-3 py-2.5">
                {phaseGroups.map((group) => (
                  <div key={group.area ?? '__none__'} className="space-y-1">
                    <p className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
                      {group.area ?? 'Ungrouped'}
                    </p>
                    <ul className="space-y-1">
                      {group.phases.map((phase) => {
                        const meta = controller.metaFor(phase.id, column.key);
                        return (
                        <li
                          key={phase.id}
                          className="flex items-center gap-2 rounded-md px-1 py-0.5"
                          style={
                            meta?.highlight
                              ? {
                                  backgroundColor: `color-mix(in oklab, ${meta.highlight} 35%, transparent)`,
                                }
                              : undefined
                          }
                          title={meta?.highlight ? 'Highlighted in the document' : undefined}
                        >
                          <span className="min-w-0 flex-1">
                            <span className="block truncate text-xs font-medium">
                              {phaseRowLabel(phase)}
                            </span>
                            <span className="block truncate text-[11px] text-muted-foreground">
                              {phase.delivery_date
                                ? formatDateInMalaysia(phase.delivery_date)
                                : 'No date'}
                            </span>
                            {meta?.deliveryDateOverride && (
                              <span className="block truncate text-[11px]">
                                <span className="text-muted-foreground line-through">
                                  {phase.delivery_date
                                    ? formatDateInMalaysia(phase.delivery_date)
                                    : '-'}
                                </span>
                                {' '}
                                <span className="font-medium">
                                  {formatDateInMalaysia(meta.deliveryDateOverride)}
                                </span>
                              </span>
                            )}
                          </span>
                          <input
                            type="text"
                            inputMode="decimal"
                            data-column-key={column.key}
                            value={controller.valueFor(phase.id, column.key)}
                            disabled={!controller.canEdit || !column.productId}
                            aria-label={`${phaseRowLabel(phase)}, ${
                              column.productCode ??
                              column.customerCode ??
                              'unidentified column'
                            }`}
                            onChange={(event) =>
                              controller.setDraft(phase.id, column.key, event.target.value)
                            }
                            onBlur={() => controller.commit(phase.id, column)}
                            className="h-8 w-20 rounded-md border border-border bg-background px-2 text-end text-xs tabular-nums outline-none focus:ring-1 focus:ring-primary disabled:cursor-not-allowed disabled:text-muted-foreground"
                          />
                        </li>
                        );
                      })}
                    </ul>
                  </div>
                ))}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

function NumberCell({
  label,
  value,
  missing,
  wrong,
  emphasise,
}: {
  label: string;
  value: string | null;
  missing?: string;
  wrong?: boolean;
  emphasise?: boolean;
}) {
  return (
    <span className="block">
      <span className="block text-[10px] uppercase tracking-wide text-muted-foreground">
        {label}
      </span>
      <span
        className={cn(
          'block tabular-nums',
          emphasise && 'font-semibold',
          wrong && 'text-destructive',
        )}
      >
        {value ?? (
          <span className="text-[11px] font-normal text-muted-foreground">
            {missing ?? 'Not given'}
          </span>
        )}
      </span>
    </span>
  );
}
