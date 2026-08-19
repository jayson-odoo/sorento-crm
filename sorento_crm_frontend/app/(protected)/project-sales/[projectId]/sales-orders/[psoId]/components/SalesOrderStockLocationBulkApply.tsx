'use client';

import * as React from 'react';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog';
import { Button } from '@/components/ui/button';
import { SearchableSelect } from '@/components/common/SearchableSelect';
import { useBulkSetLinesStockLocation } from '../../../../_shared/hooks/useProjectSalesOrders';
import { fetchWarehouseOptions } from '../../../../_shared/services/warehouseSelectService';
import type { ProjectSalesOrderLine } from '../../../../_shared/types/projectSalesOrder.types';

/**
 * Sets one warehouse code on every line of this draft, in one confirmed action (captain, 19
 * Aug 2026).
 *
 * A standalone control rather than something staged into the header's edit session: like
 * "Move lines" beside it, it acts immediately on the order as it is STORED - one PATCH per
 * line - so it works whether or not an edit session happens to be open, and there is nothing
 * left to Save afterwards.
 */
export function SalesOrderStockLocationBulkApply({
  projectId,
  psoId,
  lines,
  reference,
}: {
  projectId: string;
  psoId: string;
  lines: ProjectSalesOrderLine[];
  reference: string;
}) {
  const [code, setCode] = React.useState('');
  const [label, setLabel] = React.useState('');
  const [confirming, setConfirming] = React.useState(false);
  const apply = useBulkSetLinesStockLocation(projectId, psoId);

  if (lines.length === 0) return null;
  const count = lines.length;

  return (
    <div className="flex flex-wrap items-center gap-2 text-sm">
      <label htmlFor="so-bulk-stock-location" className="text-muted-foreground">
        Stock location for all lines
      </label>
      <SearchableSelect
        id="so-bulk-stock-location"
        value={code}
        onChange={setCode}
        onOptionChange={(option) => setLabel(option?.label ?? '')}
        selectedOption={code ? { value: code, label: label || code } : undefined}
        fetchOptions={fetchWarehouseOptions}
        clearable
        size="sm"
        placeholder="Select warehouse"
        emptyMessage="No warehouse found"
        triggerClassName="w-56"
      />
      <Button
        type="button"
        variant="outline"
        size="sm"
        disabled={!code || apply.isPending}
        onClick={() => setConfirming(true)}
      >
        Apply to all lines
      </Button>

      <AlertDialog open={confirming} onOpenChange={setConfirming}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{`Set ${code} on ${count} line${count === 1 ? '' : 's'}?`}</AlertDialogTitle>
            <AlertDialogDescription>
              {`Every line on ${reference} gets this stock location right away. It is written one line at a time and cannot be undone in one step.`}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={apply.isPending}>Cancel</AlertDialogCancel>
            <AlertDialogAction
              disabled={apply.isPending}
              onClick={(event) => {
                // Held open by hand: the dialog would otherwise close itself on click, and
                // a failure would then have nowhere to report back to.
                event.preventDefault();
                apply
                  .mutateAsync({ lineIds: lines.map((line) => line.id), stockLocation: code })
                  .then(() => setConfirming(false))
                  .catch(() => {
                    // The mutation already toasted the reason.
                  });
              }}
            >
              {apply.isPending ? 'Applying...' : 'Apply'}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
