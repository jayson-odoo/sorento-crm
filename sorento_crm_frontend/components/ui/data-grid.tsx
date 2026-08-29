'use client';

import { createContext, ReactNode, useContext } from 'react';
import { cn } from '@/lib/utils';
import { ColumnFiltersState, RowData, SortingState, Table } from '@tanstack/react-table';
import { useListingColumnPreferences } from '@/lib/listing-column-preferences/useListingColumnPreferences';
import { usePathname } from 'next/navigation';

declare module '@tanstack/react-table' {
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  interface ColumnMeta<TData extends RowData, TValue> {
    headerTitle?: string;
    headerClassName?: string;
    cellClassName?: string;
    skeleton?: ReactNode;
    expandedContent?: (row: TData) => ReactNode;
  }
}

export type DataGridApiFetchParams = {
  pageIndex: number;
  pageSize: number;
  sorting?: SortingState;
  filters?: ColumnFiltersState;
  searchQuery?: string;
};

export type DataGridApiResponse<T> = {
  data: T[];
  empty: boolean;
  pagination: {
    total: number;
    page: number;
  };
};

export interface DataGridContextProps<TData extends object> {
  props: DataGridProps<TData>;
  table: Table<TData>;
  recordCount: number;
  isLoading: boolean;
  columnPreferences?: {
    resetToDefaults?: () => Promise<void>;
  };
  isColumnPreferencesLoading?: boolean;
}

export type DataGridRequestParams = {
  pageIndex: number;
  pageSize: number;
  sorting?: SortingState;
  columnFilters?: ColumnFiltersState;
};

export interface DataGridProps<TData extends object> {
  className?: string;
  table?: Table<TData>;
  recordCount: number;
  children?: ReactNode;
  onRowClick?: (row: TData) => void;
  isLoading?: boolean;
  loadingMode?: 'skeleton' | 'spinner';
  loadingMessage?: ReactNode | string;
  emptyMessage?: ReactNode | string;
  /**
   * Optional row grouping. Return a label when `row` starts a new group, or
   * null/undefined otherwise; the grid draws a divider row above it.
   *
   * The caller owns the grouping rule. Members must already be contiguous - 
   * order them server-side - or the same group will render more than once.
   */
  renderGroupHeader?: (row: any, previousRow: any | null) => ReactNode | null;
  /**
   * Optional per-user per-listing key for persisting column visibility/order.
   * Expected to be the RBAC view permission slug (e.g. `order_management.orders.view`).
   *
   * Omitted, the grid persists under the pathname. Pass `null` to turn persistence OFF
   * entirely - the right call when the columns are data rather than a fixed set.
   */
  listingKey?: string | null;
  tableLayout?: {
    dense?: boolean;
    cellBorder?: boolean;
    rowBorder?: boolean;
    rowRounded?: boolean;
    stripped?: boolean;
    headerBackground?: boolean;
    headerBorder?: boolean;
    headerSticky?: boolean;
    width?: 'auto' | 'fixed';
    columnsVisibility?: boolean;
    columnsResizable?: boolean;
    columnsPinnable?: boolean;
    columnsMovable?: boolean;
    columnsDraggable?: boolean;
    rowsDraggable?: boolean;
  };
  tableClassNames?: {
    base?: string;
    header?: string;
    headerRow?: string;
    headerSticky?: string;
    body?: string;
    bodyRow?: string;
    footer?: string;
    edgeCell?: string;
  };
  /**
   * @deprecated No-op. The auto-rendered standard toolbar was removed - every list
   * owns its toolbar via `DataGridListToolbar` in `CardHeader`. Kept only so existing
   * `standardToolbar={false}` call-sites keep type-checking; safe to delete on touch.
   */
  standardToolbar?: boolean;
  /** @deprecated No longer wired - pass `onRefresh` to `DataGridListToolbar` instead. */
  onRefresh?: () => void | Promise<void>;
  /** @deprecated See `onRefresh`. */
  isRefreshing?: boolean;
}

const DataGridContext = createContext<
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  DataGridContextProps<any> | undefined
>(undefined);

function useDataGrid() {
  const context = useContext(DataGridContext);
  if (!context) {
    throw new Error('useDataGrid must be used within a DataGridProvider');
  }
  return context;
}

function DataGridProvider<TData extends object>({
  children,
  table,
  columnPreferences,
  isColumnPreferencesLoading,
  ...props
}: (DataGridProps<TData> & { table: Table<TData> }) & {
  columnPreferences?: {
    resetToDefaults?: () => Promise<void>;
  };
  isColumnPreferencesLoading?: boolean;
}) {
  return (
    <DataGridContext.Provider
      value={{
        props,
        table,
        recordCount: props.recordCount,
        // Keep skeleton/loading visible until user column preferences are applied
        // to avoid a default-layout flash before personalized settings load.
        isLoading: Boolean(props.isLoading || isColumnPreferencesLoading),
        columnPreferences,
        isColumnPreferencesLoading,
      }}
    >
      {children}
    </DataGridContext.Provider>
  );
}

function DataGrid<TData extends object>({ children, table, listingKey, ...props }: DataGridProps<TData>) {
  const pathname = usePathname();
  const defaultProps: Partial<DataGridProps<TData>> = {
    loadingMode: 'skeleton',
    tableLayout: {
      dense: false,
      cellBorder: false,
      rowBorder: true,
      rowRounded: false,
      stripped: false,
      headerSticky: false,
      headerBackground: true,
      headerBorder: true,
      width: 'fixed',
      // Hide/show will no longer render a dedicated panel; keep the grid header focused on sorting.
      columnsVisibility: true,
      columnsResizable: true,
      columnsPinnable: false,
      columnsMovable: false,
      // Enable column drag + drop reordering directly in the table header.
      columnsDraggable: true,
      rowsDraggable: false,
    },
    tableClassNames: {
      base: '',
      header: '',
      headerRow: '',
      headerSticky: 'sticky top-0 z-10 bg-background/90 backdrop-blur-xs',
      body: '',
      bodyRow: '',
      footer: '',
      edgeCell: '',
    },
    // Default OFF: every list owns its toolbar (DataGridListToolbar in CardHeader,
    // or a legacy per-page toolbar). The auto standard toolbar was almost always a
    // DUPLICATE of the page's own toolbar. Pages that genuinely want the built-in
    // toolbar opt in with standardToolbar set true + standardToolbarProps.
    // (Migration: docs/plans/PLAN-unified-list-toolbar.md)
    standardToolbar: false,
  };

  const mergedProps: DataGridProps<TData> = {
    ...defaultProps,
    ...props,
    tableLayout: {
      ...defaultProps.tableLayout,
      ...(props.tableLayout || {}),
    },
    tableClassNames: {
      ...defaultProps.tableClassNames,
      ...(props.tableClassNames || {}),
    },
  };

  // Ensure table is provided
  if (!table) {
    throw new Error('DataGrid requires a "table" prop');
  }

  // `listingKey={null}` is a real opt-out: nothing is fetched, applied or saved, and the
  // column menu loses its "Reset to defaults" entry because there is no config to reset.
  // A listing whose columns are DATA (the stock-debt calendar) needs this: a row saved
  // under the pathname fallback is re-applied against whichever columns happen to exist
  // when it arrives, which reorders the screen and names columns that are not there yet.
  // `undefined` keeps the pathname fallback, so every other listing is untouched.
  const persistenceDisabled = listingKey === null;
  const effectiveListingKey = persistenceDisabled ? null : (listingKey ?? pathname);

  const { resetToDefaults, isLoading: isPrefsLoading } = useListingColumnPreferences({
    table,
    listingKey: effectiveListingKey,
  });

  return (
    <DataGridProvider
      table={table}
      columnPreferences={persistenceDisabled ? undefined : { resetToDefaults }}
      isColumnPreferencesLoading={isPrefsLoading}
      {...mergedProps}
    >
      {children}
    </DataGridProvider>
  );
}

function DataGridContainer({
  children,
  className,
  border = true,
}: {
  children: ReactNode;
  className?: string;
  border?: boolean;
}) {
  return (
    <div data-slot="data-grid" className={cn('grid w-full', border && 'border border-border rounded-lg', className)}>
      {children}
    </div>
  );
}

export { useDataGrid, DataGridProvider, DataGrid, DataGridContainer, DataGridContext };
