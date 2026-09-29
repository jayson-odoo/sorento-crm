/**
 * The workbook split ANY export popover/dialog offers (PLAN-low-stock-export-split-25sep,
 * "second case" of PLAN-stock-debt-filters-totals-export-24sep R5/A7): None / Supplier /
 * Category / Supplier x Category, lifted here once a second workbook (the low stock report)
 * pays for it. `StockDebtExportPopover` renders these four options. The low stock report page
 * (PLAN-excel-preview-26sep S1) uses the same four values as pills, in the owner's order and
 * words, "Supplier and category" first because it is that page's default.
 */
export type ExportSplit = 'none' | 'supplier' | 'category' | 'supplier_category';

export const EXPORT_SPLIT_OPTIONS: { value: ExportSplit; label: string }[] = [
  { value: 'none', label: 'None' },
  { value: 'supplier', label: 'Supplier' },
  { value: 'category', label: 'Category' },
  { value: 'supplier_category', label: 'Supplier x Category' },
];
