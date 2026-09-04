'use client';

import { createContext, ReactNode, useContext, useEffect } from 'react';
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
  /**
   * Makes every body row a link to the record's own page.
   *
   * Return the bare detail path (`/order-management/orders/${row.id}`); the grid
   * appends the list state it is showing - page, limit, sort, search - so the
   * detail page's pager can walk the same page the user came from. A filter the
   * list keeps outside TanStack rides along in the returned href's own query
   * string, and wins over the grid's value.
   *
   * `onRowClick` stays for the lists whose record is edited in a lightbox.
   */
  rowHref?: (row: TData) => string;
  /**
   * True for a row with an action parked on it (D7, S6-07).
   *
   * The countdown for a row action lives in a toast, so the row itself has to say
   * which record that toast belongs to: it stays where it is, dimmed, and carries
   * `data-pending` until the server commits or the reader cancels. Read the ids
   * from `usePendingEntityKeys()`.
   */
  rowPending?: (row: TData) => boolean;
  /**
   * Extra classes layered onto a row (S4, AC-D3): a picker opened from a schedule cell
   * tints the rows whose date fell in the clicked week, so the click reads as "these rows"
   * once the dialog opens.
   */
  rowClassName?: (row: TData) => string | undefined;
  /**
   * Extra DOM attributes for a row (S4, AC-D3) - `data-bucket-hit` is the first caller.
   * Kept apart from `rowClassName` because a test (or a future reader) asserting the row's
   * own IDENTITY should not have to assert a CSS class string to do it.
   */
  rowAttributes?: (row: TData) => Record<string, string | undefined>;
  isLoading?: boolean;
  /**
   * True while the rows on screen are the PREVIOUS page's, kept visible by
   * `LIST_QUERY_OPTIONS` while the next one loads (M4 list latency).
   *
   * **Every list MUST forward it from its own list query** -
   * `const { data, isLoading, isPlaceholderData } = useOrders(params)` - because
   * this is the only signal that window emits: TanStack reports it as
   * `isLoading: false, isFetching: true, isPlaceholderData: true`, so a grid
   * left to infer the state from `isLoading` never dims at all.
   * `lib/list-query/options.inventory.test.ts` inventories the hooks that
   * spread `LIST_QUERY_OPTIONS`, walks to the files that render their grids and
   * fails on any `<DataGrid>` that does not pass this prop.
   *
   * `DataGridTable` dims the body while this is true instead of swapping it
   * for a skeleton, and `DataGridPagination` keeps its own controls live -
   * a placeholder page is not "loading" in the sense that hides the pager.
   */
  isPlaceholderData?: boolean;
  loadingMode?: 'skeleton' | 'spinner';
  loadingMessage?: ReactNode | string;
  emptyMessage?: ReactNode | string;
  /**
   * The next step an empty listing offers: the list's own Add button, usually.
   *
   * "No data available" tells the reader the grid worked and says nothing about
   * what to do, and on a list whose Add sits in a card header above a long
   * filter row that button is not where the eye is (S5-06).
   */
  emptyAction?: ReactNode;
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
  /**
   * B1 (PR #489 review round): true while a caller is driving `columnOrder`/
   * `columnVisibility` itself rather than the reader - a saved segment applying
   * (`components/list/SavedViewsMenu.tsx`) is the first user. Without it the
   * segment's own columns flow straight into the reader's PERSONAL saved layout,
   * and a published default segment (which auto-applies, AC-4.4) clobbers every
   * reader's layout the moment the page opens.
   */
  suppressPersist?: boolean;
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
    /**
     * The vertical scrollport `DataGridScroller` gives its scroller div (M5-05).
     *
     * Defaults to the `--grid-max-h` token (`css/config.reui.css`), which is
     * what makes `headerSticky` observable - a sticky header needs a bounded
     * ancestor to stick INSIDE. A string overrides it with the caller's own
     * Tailwind max-height class (a list already wrapping the grid in its own
     * bounded viewport passes its own class here instead, never both).
     * `false` removes the bound entirely (an unbounded list inside a page that
     * scrolls on its own, e.g. embedded in a dialog with its own scroll area).
     */
    scrollerMaxHeight?: string | false;
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

function DataGrid<TData extends object>({
  children,
  table,
  listingKey,
  suppressPersist,
  ...props
}: DataGridProps<TData>) {
  const pathname = usePathname();
  const defaultProps: Partial<DataGridProps<TData>> = {
    loadingMode: 'skeleton',
    tableLayout: {
      dense: false,
      cellBorder: false,
      rowBorder: true,
      rowRounded: false,
      stripped: false,
      // Absolute rule (user ruling, M5-05): every table is a DataGrid with a
      // sticky header by default. `DataGridScroller`'s own default max-height
      // (`scrollerMaxHeight`, driven by `--grid-max-h`) is what makes this
      // observable - a sticky header needs a bounded ancestor to stick inside.
      headerSticky: true,
      headerBackground: true,
      headerBorder: true,
      width: 'fixed',
      // Hide/show will no longer render a dedicated panel; keep the grid header focused on sorting.
      columnsVisibility: true,
      columnsResizable: true,
      columnsPinnable: false,
      // Absolute rule (user ruling, M5-05): "Move to Left/Right" on every
      // column header by default (31 lists already opted in). Self-contained -
      // it drives `table.setColumnOrder` from the header's own dropdown, so it
      // needs no DnD provider beyond what `columnsDraggable` already brings.
      columnsMovable: true,
      // Enable column drag + drop reordering directly in the table header.
      columnsDraggable: true,
      rowsDraggable: false,
    },
    tableClassNames: {
      base: '',
      header: '',
      headerRow: '',
      headerSticky:
        'sticky top-0 z-(--z-sticky-content) bg-background/90 backdrop-blur-xs',
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

  // Resizing that only lands on release reads as a dropped gesture. The resize
  // handler reads this option at pointer-down time, so setting it once here
  // reaches every list, including the ~70 that never passed it - and it sticks:
  // `useReactTable` merges the list's options over the PREVIOUS ones on each of
  // its renders, and no list mentions columnResizeMode, so it is never reset.
  // In an effect rather than the render body, because it mutates an object the
  // caller owns.
  useEffect(() => {
    if (table && table.options.columnResizeMode !== 'onChange') {
      table.setOptions((prev) => ({ ...prev, columnResizeMode: 'onChange' }));
    }
  }, [table]);

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
    suppressPersist,
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
