'use client';

import * as React from 'react';
import { AlertTriangle, Ban, Info } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  Popover,
  PopoverContent,
  PopoverPortal,
  PopoverTrigger,
} from '@/components/ui/popover';
import type { SearchableSelectOption } from '@/components/common/SearchableSelect';
import { FINDING_SEVERITY_LABEL } from '../../../_shared/lib/findings';
import { DismissReasonDialog } from '../../components/DismissReasonDialog';
import { columnFlag } from '../lib/scheduleTotals';
import type { ColumnState } from '../lib/scheduleTotals';
import { DeliveryScheduleProductPicker } from './DeliveryScheduleProductPicker';

/** Everything a Flag cell can do to its own column. Built once in the review client. */
export interface FlagActions {
  canEdit: boolean;
  poOptions: SearchableSelectOption[];
  resolveProduct: (columnIndex: number, productId: string) => void;
  /** Put the cursor in this column's first quantity that can be typed into. */
  fixQuantities: (columnKey: string) => void;
  /** Absent on the demo screen, which has no server to record a dismissal on. */
  dismiss?: (columnIndex: number, reason: string) => Promise<unknown>;
  undoDismiss?: (columnIndex: number) => void;
  dismissing: boolean;
}

/**
 * One column's finding, on its own row (S3-7, S5-3).
 *
 * One compact indicator, the S3 severity pill plus a count, and never a card stacked under the
 * row: the row stays one line high (owner hand test on PR #1237, 25 Sep 2026). Pressing it opens
 * a popover with one line per thing the check said, and the actions that end it: the product
 * picker or "Fix the quantities", and "Dismiss with a reason". A column that agrees has nothing
 * to open, so it is only the pill.
 */
export function DeliveryScheduleFlagCell({
  column,
  actions,
  idPrefix,
}: {
  column: ColumnState;
  actions: FlagActions;
  idPrefix: string;
}) {
  const [open, setOpen] = React.useState(false);
  const [dismissingOpen, setDismissingOpen] = React.useState(false);
  const flag = columnFlag(column);
  const name = column.productCode ?? column.customerCode ?? `column ${column.index + 1}`;

  if (flag === 'agrees') {
    return (
      <Badge variant="success" appearance="light" size="sm">
        Agrees
      </Badge>
    );
  }

  const lines = [
    ...column.blockers.map((blocker) => blocker.detail),
    ...(column.warning ? [column.warning] : []),
  ];
  const pill =
    flag === 'blocked'
      ? { label: FINDING_SEVERITY_LABEL.hard, variant: 'destructive' as const, Icon: AlertTriangle }
      : flag === 'warning'
        ? { label: FINDING_SEVERITY_LABEL.warn, variant: 'warning' as const, Icon: Info }
        : { label: 'Dismissed', variant: 'secondary' as const, Icon: Ban };

  const codes = new Set(column.blockers.map((blocker) => blocker.code));
  const editable = actions.canEdit && flag === 'blocked';
  const pickAction = codes.has('needs_product')
    ? 'Pick the product'
    : codes.has('not_on_po') && column.productId
      ? 'Pick a different product'
      : column.productId
        ? 'Change the product'
        : null;

  return (
    <>
      <Popover open={open} onOpenChange={setOpen}>
        <PopoverTrigger asChild>
          <button
            type="button"
            aria-label={`${pill.label}, ${lines.length} on ${name}`}
            title={pill.label}
            className="inline-flex max-w-full rounded-full focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-primary"
          >
            <Badge variant={pill.variant} appearance="light" size="sm" className="max-w-full">
              <pill.Icon aria-hidden />
              <span className="truncate">{pill.label}</span>
              <span className="tabular-nums">{lines.length}</span>
            </Badge>
          </button>
        </PopoverTrigger>
        <PopoverPortal>
          <PopoverContent align="start" className="w-80 space-y-2">
            <ul className="space-y-1 text-sm" data-testid="flag-lines">
              {lines.map((line) => (
                <li key={line} className="break-words">
                  {line}
                </li>
              ))}
              {column.dismissed && (
                <li className="break-words text-muted-foreground">
                  {`Dismissed${column.dismissedByName ? ` by ${column.dismissedByName}` : ''}${
                    column.dismissedReason ? `: ${column.dismissedReason}` : ''
                  }`}
                </li>
              )}
            </ul>

            {editable && (
              <div className="flex flex-wrap items-center gap-2 pt-1">
                {pickAction && (
                  <div className="w-full">
                    <DeliveryScheduleProductPicker
                      idPrefix={idPrefix}
                      columnIndex={column.index}
                      customerCode={column.customerCode}
                      action={pickAction}
                      poOptions={actions.poOptions}
                      onPick={(productId) => {
                        setOpen(false);
                        actions.resolveProduct(column.index, productId);
                      }}
                    />
                  </div>
                )}
                {column.productId && !codes.has('not_on_po') && (
                  <Button
                    type="button"
                    size="sm"
                    variant="outline"
                    onClick={() => {
                      setOpen(false);
                      actions.fixQuantities(column.key);
                    }}
                  >
                    Fix the quantities
                  </Button>
                )}
                {actions.dismiss && (
                  <Button
                    type="button"
                    size="sm"
                    variant="outline"
                    onClick={() => {
                      setOpen(false);
                      setDismissingOpen(true);
                    }}
                  >
                    Dismiss with a reason
                  </Button>
                )}
              </div>
            )}

            {actions.canEdit && column.dismissed && actions.undoDismiss && (
              <Button
                type="button"
                size="sm"
                variant="outline"
                onClick={() => {
                  setOpen(false);
                  actions.undoDismiss?.(column.index);
                }}
              >
                Undo
              </Button>
            )}
          </PopoverContent>
        </PopoverPortal>
      </Popover>

      {dismissingOpen && actions.dismiss && (
        <DismissReasonDialog
          severity="hard"
          detail={lines[0] ?? name}
          ids={[String(column.index)]}
          submitting={actions.dismissing}
          onDone={() => setDismissingOpen(false)}
          onDismiss={(_ids, reason) => actions.dismiss!(column.index, reason)}
        />
      )}
    </>
  );
}
