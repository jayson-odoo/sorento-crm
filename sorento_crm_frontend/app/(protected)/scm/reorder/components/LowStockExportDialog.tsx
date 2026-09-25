'use client';

import * as React from 'react';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Label } from '@/components/ui/label';
import { RadioGroup, RadioGroupItem } from '@/components/ui/radio-group';
import { EXPORT_SPLIT_OPTIONS, type ExportSplit } from '@/components/common/export-split';
import { useLowStockPreview } from '../hooks/useSummaryOrder';
import { previewLowStockExport } from '../services/summaryOrderService';

/**
 * The low stock report's split dialog (R3, PLAN-low-stock-export-split-25sep): the Actions
 * menu's "Low stock report Excel" item opens this instead of starting the export directly -
 * the same "small dialog before acting" pattern `ReorderPlanView`'s own "Reset planning"
 * item already uses. Same four options `StockDebtExportPopover` renders, off the shared
 * `EXPORT_SPLIT_OPTIONS`, and the same "N rows, M sheets" line, built here from
 * `useLowStockPreview` + `previewLowStockExport` rather than the popover's own
 * already-loaded envelope (AC-16b): a courtesy, not a gate - a failed read hides the line
 * and leaves Export enabled.
 */
export function LowStockExportDialog({
  open,
  onOpenChange,
  runId,
  onExport,
  pending,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  runId: string | null;
  onExport: (split: ExportSplit) => void;
  pending: boolean;
}) {
  const [split, setSplit] = React.useState<ExportSplit>('none');

  // Reset to `none` every time the dialog opens (R2's own default), never carrying the
  // previous choice across opens.
  React.useEffect(() => {
    if (open) setSplit('none');
  }, [open]);

  const previewQuery = useLowStockPreview(runId, open);
  const preview = previewLowStockExport(previewQuery.data, split);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-sm">
        <DialogHeader>
          <DialogTitle>Low stock report</DialogTitle>
          <DialogDescription>Choose how to split the workbook, then export.</DialogDescription>
        </DialogHeader>

        <DialogBody className="space-y-4">
          <div className="space-y-2">
            <Label className="text-xs text-muted-foreground">Split into sheets</Label>
            <RadioGroup
              className="gap-2"
              value={split}
              onValueChange={(value) => setSplit(value as ExportSplit)}
            >
              {EXPORT_SPLIT_OPTIONS.map((option) => (
                <label key={option.value} className="flex items-center gap-2 text-sm">
                  <RadioGroupItem value={option.value} id={`low-stock-split-${option.value}`} />
                  {option.label}
                </label>
              ))}
            </RadioGroup>
          </div>
          {previewQuery.isLoading ? (
            <p className="text-xs text-muted-foreground">...</p>
          ) : previewQuery.isError ? null : (
            <p className="text-xs text-muted-foreground">
              {preview.rows.toLocaleString()} row{preview.rows === 1 ? '' : 's'},{' '}
              {preview.sheets.toLocaleString()} sheet{preview.sheets === 1 ? '' : 's'}
            </p>
          )}
        </DialogBody>

        <DialogFooter>
          <Button variant="ghost" onClick={() => onOpenChange(false)} disabled={pending}>
            Cancel
          </Button>
          <Button onClick={() => onExport(split)} disabled={pending}>
            {pending ? 'Starting…' : 'Export'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
