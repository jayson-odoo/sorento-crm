'use client';

import * as React from 'react';
import { Download } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import { RadioGroup, RadioGroupItem } from '@/components/ui/radio-group';
import { useExportStockDebt } from '../hooks/useStockDebtQuery';
import { previewStockDebtExport } from '../services/stockDebtService';
import type { StockDebtExportParams } from '../services/stockDebtService';
import type { StockDebtExportSplit, StockDebtListResponse } from '../types/stockDebt.types';

/**
 * The board's ONE primary CTA (R12, R13): a single "Export" button that opens a small
 * popover rather than growing the toolbar with a second control. Split None / Supplier /
 * Category / Supplier x Category (R5, AC-33), a one-line rows/sheets preview built from
 * whatever the board already has loaded (`previewStockDebtExport` - no network call of its
 * own), then Export - which starts the workbook through My Downloads and never blocks on
 * the worker (AC-34).
 */

const SPLIT_OPTIONS: { value: StockDebtExportSplit; label: string }[] = [
  { value: 'none', label: 'None' },
  { value: 'supplier', label: 'Supplier' },
  { value: 'category', label: 'Category' },
  { value: 'supplier_category', label: 'Supplier x Category' },
];

export function StockDebtExportPopover({
  envelope,
  filters,
}: {
  envelope: StockDebtListResponse | undefined;
  /** The board's current filters, minus paging and split - what the export sends (AC-17). */
  filters: Omit<StockDebtExportParams, 'split'>;
}) {
  const [open, setOpen] = React.useState(false);
  const [split, setSplit] = React.useState<StockDebtExportSplit>('none');
  const exportMutation = useExportStockDebt();

  const preview = previewStockDebtExport(envelope, split);

  const handleExport = () => {
    exportMutation.mutate(
      { ...filters, split },
      { onSuccess: () => setOpen(false) },
    );
  };

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button size="sm" className="gap-1.5">
          <Download className="size-4" />
          Export
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-72 space-y-4" align="end">
        <div className="space-y-2">
          <Label className="text-xs text-muted-foreground">Split into sheets</Label>
          <RadioGroup
            className="gap-2"
            value={split}
            onValueChange={(value) => setSplit(value as StockDebtExportSplit)}
          >
            {SPLIT_OPTIONS.map((option) => (
              <label key={option.value} className="flex items-center gap-2 text-sm">
                <RadioGroupItem value={option.value} id={`export-split-${option.value}`} />
                {option.label}
              </label>
            ))}
          </RadioGroup>
        </div>
        <p className="text-xs text-muted-foreground">
          {preview.rows.toLocaleString()} row{preview.rows === 1 ? '' : 's'},{' '}
          {preview.sheets.toLocaleString()} sheet{preview.sheets === 1 ? '' : 's'}
        </p>
        <Button
          className="w-full"
          onClick={handleExport}
          disabled={exportMutation.isPending || preview.rows === 0}
        >
          {exportMutation.isPending ? 'Starting…' : 'Export'}
        </Button>
      </PopoverContent>
    </Popover>
  );
}
