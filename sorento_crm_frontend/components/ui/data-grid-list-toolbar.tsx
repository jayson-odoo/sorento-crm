'use client';

import { Fragment, ReactNode, useMemo, useState } from 'react';
import Link from 'next/link';
import type { Table } from '@tanstack/react-table';
import { Columns3, Download, Filter, MoreHorizontal, RefreshCw, X, type LucideIcon } from 'lucide-react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Checkbox } from '@/components/ui/checkbox';
import { DataGridColumnVisibility } from '@/components/ui/data-grid-column-visibility';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip';
import { ListQueryExportDialog } from '@/components/list/ListQueryExportDialog';
import { ListQueryFilterDialog } from '@/components/list/ListQueryFilterDialog';
import { generateExcelFile, type ColumnOption } from '@/lib/excel-utils';
import type { ListQueryFilterGroup, ListQueryResourceKey } from '@/lib/list-query/listQueryService';

/**
 * Canonical toolbar for every DataGrid list (see docs/plans/PLAN-unified-list-toolbar.md).
 *
 * Layout (D2), left -> right:
 *   [Search] [Filters?] [Columns] [Export]   ·····   [Secondary ▾] [Primary +Add]
 * When >=1 row is selected, the LEFT cluster is replaced by a bulk strip:
 *   [n selected] [bulk actions…] [Clear]
 * `keepSearchWhileSelected` keeps the search in front of that strip, for a list where the
 * selection is BUILT by searching (tick one order, search for the next, tick that too) and
 * losing the box on the first tick would leave no way to reach the second row. On such a
 * list the strip counts the accumulated selection, not just the loaded page's share.
 *
 * Rules baked in (so pages cannot diverge):
 *  - Filters renders ONLY when `filters` is supplied (no dead "no filters" popover). (D3)
 *  - Export is DISABLED until >=1 row is selected; click opens a column modal
 *    pre-ticked to the currently-visible columns; exports the SELECTED rows. (D4)
 *  - Secondary actions collapse into a `▾` overflow when there are >=2. (D7)
 *  - Selection is read from react-table's rowSelection (use `buildSelectColumn`).
 *
 * Place inside `<CardHeader>`. This is the ONLY sanctioned list toolbar: the
 * legacy auto-rendered `DataGridStandardToolbar` and DataGrid's `standardToolbar`
 * escape hatch were removed, so a list cannot accidentally render a second/duplicate
 * toolbar. Do NOT hand-roll a separate button row in a list CardHeader — feed slots
 * here instead.
 */

export type ToolbarAction = {
  key: string;
  label: string;
  icon?: LucideIcon;
  onClick?: () => void;
  /** When set, renders as a link instead of a button. */
  href?: string;
  disabled?: boolean;
  /** Tooltip shown when disabled. */
  disabledReason?: string;
  destructive?: boolean;
  /** Optional `data-guide-target` for user-guide deep-link spotlighting. */
  dataGuideTarget?: string;
};

export type ListToolbarFilters =
  | {
      kind: 'listQuery';
      resourceKey: ListQueryResourceKey;
      getPayload: () => Record<string, unknown>;
      advancedFilter: ListQueryFilterGroup | null;
      onApply: (filter: ListQueryFilterGroup | null) => void;
      workflowDefinitionId?: string | null;
    }
  | {
      kind: 'custom';
      /** Whether any custom filter is currently active (drives the "On" badge + count). */
      active?: boolean;
      activeCount?: number;
      content: ReactNode;
    };

export type ListToolbarExport<TData extends object> = {
  filename?: string;
  /**
   * All-records (server) export. Used when the user has chosen "select all N
   * records" via the banner (`selectAllMatching.active`): streams the full
   * filtered set server-side with the chosen columns instead of building from
   * the loaded page rows. (D4/F)
   */
  allRecords?: {
    /** Stream the full filtered set with the chosen column ids. Resolves when the download starts. */
    onExport: (selectedColumnIds: string[]) => Promise<void> | void;
  };
};

/**
 * Server-side ListQuery export (orders/products/suppliers/promotions/workflows).
 * Opens `ListQueryExportDialog` which exports the full FILTERED set server-side
 * with column selection — this already satisfies "export reflects columns / full
 * set", so it is intentionally NOT selection-gated (deviation from D4, documented
 * in the plan). If rows ARE selected they are passed as `selectedRecordIds`.
 */
export type ListToolbarListQueryExport = {
  kind: 'listQuery';
  resourceKey: ListQueryResourceKey;
  getPayload: () => Record<string, unknown>;
  filename?: string;
  workflowDefinitionId?: string | null;
};

/**
 * Drives the "select all N records" banner (Odoo pattern, D4/F). The page owns
 * the `active` boolean; when the user selects all rows on the page AND more rows
 * exist beyond the loaded page, the banner offers to extend the selection to the
 * entire filtered set. While active, Export uses the server all-records path.
 */
export type ListToolbarSelectAllMatching = {
  /** Total rows matching the current filters (across all pages). */
  total: number;
  /** Rows currently loaded into the grid (the current page). */
  loadedCount: number;
  /** True when the user has opted into selecting the full filtered set. */
  active: boolean;
  onSelectAll: () => void;
  onClear: () => void;
};

export type DataGridListToolbarProps<TData extends object> = {
  table: Table<TData>;
  /** Search input (already wired to state by the page). */
  searchSlot?: ReactNode;
  /**
   * Keep `searchSlot` visible while the bulk strip is up (default false, so every other
   * listing is unchanged). Opt in on a list where the selection is assembled ACROSS
   * searches - the fulfilment worklist's "Plan together", where the two orders to plan are
   * found by two different needles and the first tick would otherwise remove the box.
   * It also makes the strip's count the WHOLE selection rather than the loaded page's share
   * of it, so "1 selected" cannot sit beside a "Plan together (2)".
   */
  keepSearchWhileSelected?: boolean;
  /** Omit to hide the Filters button entirely (D3). */
  filters?: ListToolbarFilters;
  /** Export config, or `false` to hide Export. Default: selection-gated client export;
   *  pass a `{kind:'listQuery'}` config for server-side filtered-set export. */
  exportConfig?: ListToolbarExport<TData> | ListToolbarListQueryExport | false;
  /** Show the Columns personalization button. Default true. */
  showColumns?: boolean;
  /** Optional manual refresh (wire to React Query refetch). Renders after Columns. */
  onRefresh?: () => void | Promise<void>;
  isRefreshing?: boolean;
  /** Primary call-to-action (e.g. the "Add" button). Anchored to the right edge. */
  primaryAction?: ReactNode;
  /** Secondary actions (Import, attachment links, templates). Overflow `▾` at >=2 (D7). */
  secondaryActions?: ToolbarAction[];
  /** Bulk actions shown in the bulk strip when rows are selected (H). */
  bulkActions?: ToolbarAction[];
  /**
   * Custom bulk strip content (overrides `bulkActions` AND the auto Export button)
   * — for pages that consolidate all bulk actions into a single "Action" dropdown
   * with selection-dependent gating (e.g. the Unified Drive, UAC F2). The slot is
   * rendered between the "N selected" badge and the Clear button.
   *
   * May be a render function receiving `{ openExport }` so the page's own "Action"
   * menu can reuse the toolbar's selected-rows Export dialog instead of a separate
   * Export button.
   */
  bulkActionsSlot?: ReactNode | ((api: { openExport: () => void }) => ReactNode);
  /** "Select all N records" banner config (D4/F). Omit to disable cross-page selection. */
  selectAllMatching?: ListToolbarSelectAllMatching;
};

function ActionButton({ action }: { action: ToolbarAction }) {
  const Icon = action.icon;
  const inner = (
    <>
      {Icon ? <Icon className="size-4" /> : null}
      {action.label}
    </>
  );
  const className = action.destructive
    ? 'gap-1.5 text-destructive border-destructive/50 hover:bg-destructive/10'
    : 'gap-1.5';
  if (action.href && !action.disabled) {
    return (
      <Button variant="outline" size="sm" className={className} asChild>
        <Link href={action.href} data-guide-target={action.dataGuideTarget}>
          {inner}
        </Link>
      </Button>
    );
  }
  const btn = (
    <Button
      variant="outline"
      size="sm"
      className={className}
      onClick={action.onClick}
      disabled={action.disabled}
      data-guide-target={action.dataGuideTarget}
    >
      {inner}
    </Button>
  );
  if (action.disabled && action.disabledReason) {
    return (
      <Tooltip>
        <TooltipTrigger asChild>
          <span tabIndex={0}>{btn}</span>
        </TooltipTrigger>
        <TooltipContent>{action.disabledReason}</TooltipContent>
      </Tooltip>
    );
  }
  return btn;
}

export function DataGridListToolbar<TData extends object>({
  table,
  searchSlot,
  keepSearchWhileSelected = false,
  filters,
  exportConfig,
  showColumns = true,
  primaryAction,
  secondaryActions = [],
  bulkActions = [],
  bulkActionsSlot,
  selectAllMatching,
  onRefresh,
  isRefreshing = false,
}: DataGridListToolbarProps<TData>) {
  const [filterOpen, setFilterOpen] = useState(false);
  const [exportOpen, setExportOpen] = useState(false);
  const [selectedColumnIds, setSelectedColumnIds] = useState<Set<string>>(new Set());

  const selectedRows = table.getSelectedRowModel().rows;
  const selectedCount = selectedRows.length;
  const hasSelection = selectedCount > 0;
  /**
   * What the strip SAYS is selected.
   *
   * Page-scoped by default, because that is what a bulk action here operates on and a
   * count that promised more would be a footgun on a destructive one. A page that opted
   * into building its selection across searches is counting the SET instead, so the strip
   * agrees with its own action button rather than reporting the last search's share of it.
   * Export is deliberately NOT moved onto this: it still builds rows from the loaded ones.
   */
  const stripSelectionCount = keepSearchWhileSelected
    ? Object.values(table.getState().rowSelection).filter(Boolean).length
    : selectedCount;

  const isListQueryExport =
    exportConfig !== false && exportConfig != null && 'kind' in exportConfig && exportConfig.kind === 'listQuery';
  // The selection-gated client export config (null when export is off or listQuery).
  const selectionExport =
    exportConfig !== false && exportConfig != null && !('kind' in exportConfig) ? exportConfig : null;
  const listQueryExport =
    exportConfig !== false && exportConfig != null && 'kind' in exportConfig ? exportConfig : null;
  const allRecordsActive = Boolean(selectAllMatching?.active);
  // ListQuery export is always available (filtered-set, server-side). Selection
  // export is gated on having a selection (or the all-records banner). (D4)
  const exportEnabled = exportConfig !== false && (isListQueryExport || hasSelection || allRecordsActive);

  // Columns eligible for export — exclude the structural select/actions columns.
  const exportableColumns = useMemo(
    () =>
      table
        .getAllLeafColumns()
        .filter((c) => c.id !== 'select' && c.id !== 'actions' && c.columnDef.enableHiding !== false),
    [table],
  );

  const columnLabel = (id: string): string => {
    const col = table.getColumn(id);
    const metaTitle = col?.columnDef.meta?.headerTitle;
    if (metaTitle) return metaTitle;
    const header = col?.columnDef.header;
    if (typeof header === 'string') return header;
    return id;
  };

  const openExport = () => {
    // Pre-tick = currently VISIBLE export columns (mirrors Columns personalization). (D4)
    setSelectedColumnIds(new Set(exportableColumns.filter((c) => c.getIsVisible()).map((c) => c.id)));
    setExportOpen(true);
  };

  const runExport = async () => {
    const chosen = Array.from(selectedColumnIds);
    if (!chosen.length) {
      toast.error('Select at least one column');
      return;
    }
    try {
      // All-records server export path (D4/F): full filtered set, fetched
      // server-side, never the loaded page rows.
      if (allRecordsActive && selectionExport?.allRecords) {
        await selectionExport.allRecords.onExport(chosen);
        setExportOpen(false);
        return;
      }
      // Page-scope client export of the SELECTED rows.
      const data = selectedRows.map((row) => {
        const out: Record<string, unknown> = {};
        for (const id of chosen) out[id] = row.getValue(id);
        return out;
      });
      const cols: ColumnOption[] = chosen.map((id) => ({ key: id, label: columnLabel(id), selected: true }));
      const filename = selectionExport?.filename || 'export.xlsx';
      await generateExcelFile(data, cols, filename);
      toast.success(`Exported ${selectedRows.length} row(s)`);
      setExportOpen(false);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Export failed');
    }
  };

  const exportCountLabel = allRecordsActive && selectAllMatching ? selectAllMatching.total : selectedCount;

  // Banner shows once every loaded row is selected AND more rows exist beyond the page.
  const allPageRowsSelected = table.getIsAllPageRowsSelected();
  const showSelectAllBanner =
    Boolean(selectAllMatching) &&
    (allRecordsActive || (allPageRowsSelected && hasSelection && selectAllMatching!.total > selectAllMatching!.loadedCount));

  // The left cluster flips to the bulk strip whenever there is a selection
  // (page rows or the full filtered set). Export lives in BOTH places — gated
  // off in the normal cluster, enabled inside the bulk strip.
  const bulkStripActive = hasSelection || allRecordsActive;

  const clearSelection = () => {
    table.resetRowSelection();
    selectAllMatching?.onClear();
  };

  const exportButtonEl =
    exportConfig === false ? null : exportEnabled ? (
      <Button
        variant="outline"
        size="sm"
        className="gap-1.5"
        onClick={isListQueryExport ? () => setExportOpen(true) : openExport}
      >
        <Download className="size-4" />
        Export
      </Button>
    ) : (
      <Tooltip>
        <TooltipTrigger asChild>
          <span tabIndex={0}>
            <Button variant="outline" size="sm" className="gap-1.5" disabled>
              <Download className="size-4" />
              Export
            </Button>
          </span>
        </TooltipTrigger>
        <TooltipContent>Select one or more rows to export</TooltipContent>
      </Tooltip>
    );

  return (
    <TooltipProvider>
     <div className="flex w-full flex-col gap-2 py-5">
      <div className="flex w-full flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        {/* LEFT cluster — replaced by the bulk strip while rows are selected (D2/H). */}
        {bulkStripActive ? (
          <div className="flex flex-wrap items-center gap-2">
            {/* Where the box already sits when nothing is selected, so it does not move
                under the cursor the moment a row is ticked. */}
            {keepSearchWhileSelected ? searchSlot : null}
            <Badge variant="secondary" className="h-8 gap-1 px-2.5 text-sm">
              {allRecordsActive && selectAllMatching
                ? `All ${selectAllMatching.total} selected`
                : `${stripSelectionCount} selected`}
            </Badge>
            {bulkActionsSlot == null && exportButtonEl}
            {/* Bulk destructive actions operate on the loaded selection only; hide
                them once the user opts into the full filtered set to avoid a
                "delete all matching but only loaded rows go" footgun. */}
            {bulkActionsSlot != null
              ? typeof bulkActionsSlot === 'function'
                ? bulkActionsSlot({ openExport: isListQueryExport ? () => setExportOpen(true) : openExport })
                : bulkActionsSlot
              : !allRecordsActive &&
                bulkActions.map((action) => <ActionButton key={action.key} action={action} />)}
            <Button
              variant="ghost"
              size="sm"
              className="gap-1.5 text-muted-foreground"
              onClick={clearSelection}
            >
              <X className="size-4" />
              Clear
            </Button>
          </div>
        ) : (
          <div className="flex flex-wrap items-center gap-2">
            {searchSlot}
            {filters ? (
              filters.kind === 'listQuery' ? (
                <Button variant="outline" size="sm" className="gap-1.5" onClick={() => setFilterOpen(true)}>
                  <Filter className="size-4" />
                  Filters
                  {filters.advancedFilter ? (
                    <Badge variant="secondary" className="ms-0.5 px-1 py-0 text-[10px]">On</Badge>
                  ) : null}
                </Button>
              ) : (
                <DropdownMenu>
                  <DropdownMenuTrigger asChild>
                    <Button variant="outline" size="sm" className="gap-1.5">
                      <Filter className="size-4" />
                      Filters
                      {filters.active ? (
                        <Badge variant="secondary" className="ms-0.5 px-1 py-0 text-[10px]">
                          {filters.activeCount ?? 'On'}
                        </Badge>
                      ) : null}
                    </Button>
                  </DropdownMenuTrigger>
                  <DropdownMenuContent align="start" className="w-72 p-3">
                    {filters.content}
                  </DropdownMenuContent>
                </DropdownMenu>
              )
            ) : null}
            {showColumns ? (
              <DataGridColumnVisibility
                table={table}
                trigger={
                  <Button variant="outline" size="sm" className="gap-1.5">
                    <Columns3 className="size-4" />
                    Columns
                  </Button>
                }
              />
            ) : null}
            {exportButtonEl}
            {onRefresh ? (
              <Button
                type="button"
                variant="outline"
                size="sm"
                mode="icon"
                title="Refresh list"
                onClick={() => void onRefresh()}
                disabled={isRefreshing}
              >
                <RefreshCw className={`size-4 ${isRefreshing ? 'animate-spin' : ''}`} />
              </Button>
            ) : null}
          </div>
        )}

        {/* RIGHT cluster — secondary overflow + primary CTA (always present). */}
        <div className="flex flex-wrap items-center gap-2">
          {secondaryActions.length === 1 ? (
            <ActionButton action={secondaryActions[0]} />
          ) : secondaryActions.length >= 2 ? (
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button variant="outline" size="sm" className="gap-1.5">
                  <MoreHorizontal className="size-4" />
                  Actions
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end">
                {secondaryActions.map((action) => {
                  const Icon = action.icon;
                  const item = (
                    <DropdownMenuItem
                      key={action.key}
                      disabled={action.disabled}
                      onClick={action.onClick}
                      className={action.destructive ? 'text-destructive' : undefined}
                      asChild={Boolean(action.href && !action.disabled)}
                      data-guide-target={action.href && !action.disabled ? undefined : action.dataGuideTarget}
                      // The collapsed-into-"Actions" path has no room for the single-button
                      // path's `Tooltip` wrapper, so a disabled item's reason travels as a
                      // native `title` instead - still a tooltip, just the browser's own.
                      title={action.disabled ? action.disabledReason : undefined}
                    >
                      {action.href && !action.disabled ? (
                        <Link href={action.href} data-guide-target={action.dataGuideTarget}>
                          {Icon ? <Icon className="size-4" /> : null}
                          {action.label}
                        </Link>
                      ) : (
                        <Fragment>
                          {Icon ? <Icon className="size-4" /> : null}
                          {action.label}
                        </Fragment>
                      )}
                    </DropdownMenuItem>
                  );
                  return item;
                })}
              </DropdownMenuContent>
            </DropdownMenu>
          ) : null}
          {primaryAction}
        </div>
      </div>

      {/* "Select all N records" banner (Odoo pattern, D4/F). */}
      {showSelectAllBanner && selectAllMatching ? (
        <div className="flex flex-wrap items-center justify-center gap-2 rounded-md border border-dashed bg-muted/40 px-3 py-1.5 text-sm">
          {allRecordsActive ? (
            <>
              <span>
                All <span className="font-medium">{selectAllMatching.total}</span> records matching the current filters are selected.
              </span>
              <Button variant="link" size="sm" className="h-auto p-0" onClick={clearSelection}>
                Clear selection
              </Button>
            </>
          ) : (
            <>
              <span>
                All <span className="font-medium">{selectAllMatching.loadedCount}</span> on this page selected.
              </span>
              <Button variant="link" size="sm" className="h-auto p-0" onClick={selectAllMatching.onSelectAll}>
                Select all {selectAllMatching.total} records
              </Button>
            </>
          )}
        </div>
      ) : null}
     </div>

      {/* Column-selection export modal — pre-ticked to visible columns (D4).
          Only for selection (client) export; listQuery uses its own dialog below. */}
      {!isListQueryExport && (
      <Dialog open={exportOpen} onOpenChange={setExportOpen}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>Export</DialogTitle>
            <DialogDescription>
              Choose the columns to include. Exporting {exportCountLabel} row(s).
            </DialogDescription>
          </DialogHeader>
          <div className="max-h-[50vh] space-y-2 overflow-y-auto rounded-md border p-2">
            {exportableColumns.map((col) => {
              const checked = selectedColumnIds.has(col.id);
              return (
                <label
                  key={col.id}
                  className="flex cursor-pointer items-center gap-2 rounded-sm px-1 py-1.5 hover:bg-muted/60"
                >
                  <Checkbox
                    checked={checked}
                    onCheckedChange={() =>
                      setSelectedColumnIds((prev) => {
                        const next = new Set(prev);
                        if (next.has(col.id)) next.delete(col.id);
                        else next.add(col.id);
                        return next;
                      })
                    }
                  />
                  <span className="text-sm">{columnLabel(col.id)}</span>
                </label>
              );
            })}
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setExportOpen(false)}>
              Cancel
            </Button>
            <Button onClick={runExport}>Download Excel</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
      )}

      {/* ListQuery server export dialog (filtered set, column selection). */}
      {listQueryExport ? (
        <ListQueryExportDialog
          resourceKey={listQueryExport.resourceKey}
          open={exportOpen}
          onOpenChange={setExportOpen}
          filename={listQueryExport.filename}
          getPayload={listQueryExport.getPayload}
          selectedRecordIds={hasSelection ? selectedRows.map((r) => r.id) : undefined}
          workflowDefinitionId={listQueryExport.workflowDefinitionId}
        />
      ) : null}

      {/* ListQuery advanced filter dialog (server-side, canonical). */}
      {filters?.kind === 'listQuery' ? (
        <ListQueryFilterDialog
          resourceKey={filters.resourceKey}
          open={filterOpen}
          onOpenChange={setFilterOpen}
          initialFilter={filters.advancedFilter}
          onApply={filters.onApply}
          workflowDefinitionId={filters.workflowDefinitionId}
        />
      ) : null}
    </TooltipProvider>
  );
}
