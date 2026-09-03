'use client';

import { useState, useMemo } from 'react';
import { Download, X } from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Checkbox } from '@/components/ui/checkbox';
import { Label } from '@/components/ui/label';
import { ScrollArea } from '@/components/ui/scroll-area';
import { generateExcelFile, type ColumnOption } from '@/lib/excel-utils';
import { toast } from '@/lib/toast';

interface TemplateDownloadDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  data: any[];
  columns: ColumnOption[];
  filename: string;
  onColumnsChange?: (columns: ColumnOption[]) => void;
}

export function TemplateDownloadDialog({
  open,
  onOpenChange,
  data,
  columns: initialColumns,
  filename,
  onColumnsChange,
}: TemplateDownloadDialogProps) {
  const [columns, setColumns] = useState<ColumnOption[]>(initialColumns);
  const [isExporting, setIsExporting] = useState(false);

  const handleToggleColumn = (key: string) => {
    const updatedColumns = columns.map(col =>
      col.key === key ? { ...col, selected: !col.selected } : col
    );
    setColumns(updatedColumns);
    onColumnsChange?.(updatedColumns);
  };

  const handleSelectAll = () => {
    const allSelected = columns.every(col => col.selected);
    const updatedColumns = columns.map(col => ({ ...col, selected: !allSelected }));
    setColumns(updatedColumns);
    onColumnsChange?.(updatedColumns);
  };

  const handleExport = async () => {
    const selectedCount = columns.filter(col => col.selected).length;
    if (selectedCount === 0) {
      toast.error('Please select at least one column to export');
      return;
    }

    setIsExporting(true);
    try {
      await generateExcelFile(data, columns, filename);
      toast.success('Excel file downloaded successfully');
      onOpenChange(false);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Failed to export Excel file');
    } finally {
      setIsExporting(false);
    }
  };

  const selectedCount = columns.filter(col => col.selected).length;
  const allSelected = columns.length > 0 && columns.every(col => col.selected);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>Select Columns to Export</DialogTitle>
          <DialogDescription>
            Choose which columns you want to include in the Excel file.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-4">
          <div className="flex items-center justify-between border-b pb-2">
            <Label className="text-sm font-medium">
              {selectedCount} of {columns.length} columns selected
            </Label>
            <Button
              variant="ghost"
              size="sm"
              onClick={handleSelectAll}
            >
              {allSelected ? 'Deselect All' : 'Select All'}
            </Button>
          </div>
          <ScrollArea className="h-64">
            <div className="space-y-2">
              {columns.map((column) => (
                <div
                  key={column.key}
                  className="flex items-center space-x-2 p-2 hover:bg-muted/50 rounded"
                >
                  <Checkbox
                    id={column.key}
                    checked={column.selected}
                    onCheckedChange={() => handleToggleColumn(column.key)}
                  />
                  <Label
                    htmlFor={column.key}
                    className="flex-1 cursor-pointer text-sm"
                  >
                    {column.label}
                  </Label>
                </div>
              ))}
            </div>
          </ScrollArea>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button onClick={handleExport} disabled={isExporting || selectedCount === 0}>
            <Download className="size-4 mr-2" />
            {isExporting ? 'Exporting...' : 'Export to Excel'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
