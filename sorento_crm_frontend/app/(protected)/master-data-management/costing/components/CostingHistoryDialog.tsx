'use client';

import { Dialog, DialogBody, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { useCostingHistory } from '../hooks/useCosting';
import { METHOD_LABEL, money, shortDate, TRANSPORT_LABEL } from '../lib/format';
import type { CostMethod, HistoryEntry, TransportMode } from '../types/costing.types';

const FIELD_LABEL: Record<string, string> = {
  markup_pct: 'Mark-up',
  transport_mode: 'Transport mode',
  transport_value: 'Transport value',
  cost_method: 'Cost method',
  cost_method_supplier_id: 'Supplier',
};

function shown(field: string, value: HistoryEntry['old']): string {
  if (value === null || value === undefined || value === '') return 'none';
  if (field === 'markup_pct') return `${money(Number(value))} %`;
  if (field === 'transport_value') return money(Number(value));
  if (field === 'cost_method') return METHOD_LABEL[value as CostMethod] ?? String(value);
  if (field === 'transport_mode') return TRANSPORT_LABEL[value as TransportMode] ?? String(value);
  return String(value);
}

/** Who changed a row's mark-up, transport or cost method, when, and from what (AC-CG-11). */
export function CostingHistoryDialog({
  open,
  onOpenChange,
  productId,
  productCode,
  partyId,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  productId: string | null;
  productCode: string;
  partyId: string | null;
}) {
  const { data, isLoading, isError, error } = useCostingHistory(open ? productId : null, partyId);
  const entries = data?.data ?? [];

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg" aria-describedby={undefined}>
        <DialogHeader>
          <DialogTitle className="pe-8 break-words">History of {productCode}</DialogTitle>
          <DialogDescription className="sr-only">Changes to mark-up, transport and cost method.</DialogDescription>
        </DialogHeader>
        <DialogBody className="max-h-[70dvh] overflow-y-auto">
          {isError ? (
            <p className="text-sm text-destructive">
              {error instanceof Error ? error.message : 'Failed to load the history.'}
            </p>
          ) : isLoading ? null : entries.length ? (
            <ul className="divide-y rounded-lg border">
              {entries.map((e, i) => (
                <li key={`${e.changed_at}-${e.field}-${i}`} className="flex flex-col gap-0.5 px-3 py-2 text-sm">
                  <div className="flex flex-wrap items-baseline justify-between gap-x-3">
                    <span className="font-medium">{e.user_name}</span>
                    <span className="text-xs text-muted-foreground">{shortDate(e.changed_at)}</span>
                  </div>
                  <div className="min-w-0 break-words">
                    {FIELD_LABEL[e.field] ?? e.field}: {shown(e.field, e.old)} to {shown(e.field, e.new)}
                  </div>
                </li>
              ))}
            </ul>
          ) : (
            <div className="rounded-lg border border-dashed py-6 text-center">
              <p className="text-sm font-medium">No changes yet</p>
              <p className="text-xs text-muted-foreground">Edits to this row appear here.</p>
            </div>
          )}
        </DialogBody>
      </DialogContent>
    </Dialog>
  );
}

export default CostingHistoryDialog;
