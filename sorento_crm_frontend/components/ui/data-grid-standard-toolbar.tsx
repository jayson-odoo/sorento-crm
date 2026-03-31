'use client';

import { ReactNode, useMemo, useState } from 'react';
import type { Table } from '@tanstack/react-table';
import { Columns3, Download, Filter } from 'lucide-react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { DataGridColumnVisibility } from '@/components/ui/data-grid-column-visibility';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import { Checkbox } from '@/components/ui/checkbox';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { generateExcelFile, type ColumnOption } from '@/lib/excel-utils';
import { ListQueryExportDialog } from '@/components/list/ListQueryExportDialog';
import { ListQueryFilterDialog } from '@/components/list/ListQueryFilterDialog';
import type { ListQueryFilterGroup, ListQueryResourceKey } from '@/lib/list-query/listQueryService';

function toHeaderLabel(col: ReturnType<Table<object>['getAllLeafColumns']>[number]): string {
  const metaTitle = col.columnDef.meta?.headerTitle;
  if (metaTitle) return metaTitle;
  if (typeof col.columnDef.header === 'string') return col.columnDef.header;
  return col.id;
}

function normalizeCellValue(value: unknown): string | number {
  if (value === null || value === undefined) return '';
  if (typeof value === 'number' || typeof value === 'string') return value;
  if (value instanceof Date) return value.toISOString();
  if (typeof value === 'boolean') return value ? 'true' : 'false';
  try {
    return JSON.stringify(value);
  } catch {
    return String(value);
  }
}

type StandardExportConfig<TData extends object> = {
  filename?: string;
  onExport?: (ctx: {
    table: Table<TData>;
    selectedColumnIds: string[];
  }) => Promise<void> | void;
};

type StandardAdvancedFiltersConfig = {
  active?: boolean;
  content?: ReactNode;
};

export type DataGridStandardToolbarProps<TData extends object> = {
  table: Table<TData>;
  searchSlot?: ReactNode;
  quickFiltersSlot?: ReactNode;
  primaryActionsSlot?: ReactNode;
  secondaryActionsSlot?: ReactNode;
  exportConfig?: StandardExportConfig<TData>;
  advancedFilters?: StandardAdvancedFiltersConfig;
  showExport?: boolean;
  showAdvancedFilters?: boolean;
  showColumnVisibility?: boolean;
  listQueryConfig?: {
    resourceKey: ListQueryResourceKey;
    getPayload: () => Record<string, unknown>;
    selectedRecordIds?: string[];
    exportFilename?: string;
    workflowDefinitionId?: string | null;
    advancedFilter: ListQueryFilterGroup | null;
    onAdvancedFilterApply: (filter: ListQueryFilterGroup | null) => void;
  };
};

export function DataGridStandardToolbar<TData extends object>({
  table,
  searchSlot,
  quickFiltersSlot,
  primaryActionsSlot,
  secondaryActionsSlot,
  exportConfig,
  advancedFilters,
  showExport = true,
  showAdvancedFilters = true,
  showColumnVisibility = true,
  listQueryConfig,
}: DataGridStandardToolbarProps<TData>) {
  const [exportOpen, setExportOpen] = useState(false);
  const [advancedFilterOpen, setAdvancedFilterOpen] = useState(false);
  const [selectedColumnIds, setSelectedColumnIds] = useState<Set<string>>(new Set());

  const exportableColumns = useMemo(
    () =>
      table
        .getAllLeafColumns()
        .filter((col) => col.id !== 'actions' && col.id !== 'select' && col.columnDef.enableHiding !== false),
    [table],
  );

  const openExport = () => {
    setSelectedColumnIds(new Set(exportableColumns.map((c) => c.id)));
    setExportOpen(true);
  };

  const handleExport = async () => {
    const chosen = Array.from(selectedColumnIds);
    if (!chosen.length) {
      toast.error('Select at least one column');
      return;
    }

    try {
      if (exportConfig?.onExport) {
        await exportConfig.onExport({ table, selectedColumnIds: chosen });
        setExportOpen(false);
        return;
      }

      const rows = table.getRowModel().rows;
      const data = rows.map((row) => {
        const out: Record<string, string | number> = {};
        for (const colId of chosen) {
          out[colId] = normalizeCellValue(row.getValue(colId));
        }
        return out;
      });
      const cols: ColumnOption[] = exportableColumns
        .filter((c) => chosen.includes(c.id))
        .map((c) => ({ key: c.id, label: toHeaderLabel(c as any), selected: true }));
      await generateExcelFile(data, cols, exportConfig?.filename ?? 'table_export.xlsx');
      toast.success(`Exported ${rows.length} row(s)`);
      setExportOpen(false);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Export failed');
    }
  };

  return (
    <>
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex flex-wrap items-center gap-2">
          {searchSlot}
          {quickFiltersSlot}
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {secondaryActionsSlot}
          {showAdvancedFilters &&
            (listQueryConfig ? (
              <Button variant="outline" size="sm" className="gap-1" onClick={() => setAdvancedFilterOpen(true)}>
                <Filter className="size-4" />
                Filters
                {listQueryConfig.advancedFilter ? (
                  <Badge variant="secondary" className="ms-0.5 px-1 py-0 text-[10px]">
                    On
                  </Badge>
                ) : null}
              </Button>
            ) : (
              <Popover>
                <PopoverTrigger asChild>
                  <Button variant="outline" size="sm" className="gap-1">
                    <Filter className="size-4" />
                    Filters
                    {advancedFilters?.active ? (
                      <Badge variant="secondary" className="ms-0.5 px-1 py-0 text-[10px]">
                        On
                      </Badge>
                    ) : null}
                  </Button>
                </PopoverTrigger>
                <PopoverContent className="w-80" align="end">
                  {advancedFilters?.content ?? (
                    <p className="text-sm text-muted-foreground">No advanced filters configured for this table.</p>
                  )}
                </PopoverContent>
              </Popover>
            ))}
          {showExport && (
            <Button
              variant="outline"
              size="sm"
              className="gap-1"
              onClick={listQueryConfig ? () => setExportOpen(true) : openExport}
            >
              <Download className="size-4" />
              Export
            </Button>
          )}
          {showColumnVisibility && (
            <DataGridColumnVisibility
              table={table}
              trigger={
                <Button variant="outline" size="sm" className="gap-1">
                  <Columns3 className="size-4" />
                  Columns
                </Button>
              }
            />
          )}
          {primaryActionsSlot}
        </div>
      </div>

      {!listQueryConfig && (
        <Dialog open={exportOpen} onOpenChange={setExportOpen}>
          <DialogContent className="max-w-md">
            <DialogHeader>
              <DialogTitle>Export</DialogTitle>
              <DialogDescription>Choose columns to include in export.</DialogDescription>
            </DialogHeader>
            <div className="max-h-[50vh] space-y-2 overflow-y-auto rounded-md border p-2">
              {exportableColumns.map((col) => {
                const checked = selectedColumnIds.has(col.id);
                return (
                  <label key={col.id} className="flex cursor-pointer items-center gap-2 rounded-sm px-1 py-1.5 hover:bg-muted/60">
                    <Checkbox
                      checked={checked}
                      onCheckedChange={() => {
                        setSelectedColumnIds((prev) => {
                          const next = new Set(prev);
                          if (next.has(col.id)) next.delete(col.id);
                          else next.add(col.id);
                          return next;
                        });
                      }}
                    />
                    <span className="text-sm">{toHeaderLabel(col as any)}</span>
                  </label>
                );
              })}
            </div>
            <DialogFooter>
              <Button variant="outline" onClick={() => setExportOpen(false)}>
                Cancel
              </Button>
              <Button onClick={handleExport}>Download Excel</Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      )}
      {listQueryConfig && (
        <>
          <ListQueryFilterDialog
            resourceKey={listQueryConfig.resourceKey}
            open={advancedFilterOpen}
            onOpenChange={setAdvancedFilterOpen}
            initialFilter={listQueryConfig.advancedFilter}
            onApply={listQueryConfig.onAdvancedFilterApply}
            workflowDefinitionId={listQueryConfig.workflowDefinitionId}
          />
          <ListQueryExportDialog
            resourceKey={listQueryConfig.resourceKey}
            open={exportOpen}
            onOpenChange={setExportOpen}
            filename={listQueryConfig.exportFilename}
            selectedRecordIds={listQueryConfig.selectedRecordIds}
            getPayload={listQueryConfig.getPayload}
            workflowDefinitionId={listQueryConfig.workflowDefinitionId}
          />
        </>
      )}
    </>
  );
}
