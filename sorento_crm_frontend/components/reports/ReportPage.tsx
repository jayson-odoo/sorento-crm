'use client';

import { Fragment, useEffect, useMemo, useState } from 'react';
import { useSearchParams } from 'next/navigation';
import {
  type ColumnDef,
  type PaginationState,
  type SortingState,
  type VisibilityState,
  getCoreRowModel,
  getPaginationRowModel,
  getSortedRowModel,
  useReactTable,
} from '@tanstack/react-table';
import { Check, Download, Settings2 } from 'lucide-react';
import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbLink,
  BreadcrumbList,
  BreadcrumbPage,
  BreadcrumbSeparator,
} from '@/components/ui/breadcrumb';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardFooter, CardHeader, CardTable } from '@/components/ui/card';
import { DataGrid } from '@/components/ui/data-grid';
import { DataGridColumnHeader } from '@/components/ui/data-grid-column-header';
import { DataGridListToolbar } from '@/components/ui/data-grid-list-toolbar';
import { DataGridPagination } from '@/components/ui/data-grid-pagination';
import { DataGridTable } from '@/components/ui/data-grid-table';
import { ScrollArea, ScrollBar } from '@/components/ui/scroll-area';
import { Skeleton } from '@/components/ui/skeleton';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Container } from '@/components/common/container';
import { Toolbar, ToolbarActions, ToolbarHeading, ToolbarTitle } from '@/components/common/toolbar';
import { formatDateSafe, formatMoney2dp } from '@/lib/helpers';
import { useReportExport, useReportMeta, useReportRun, useReportViews } from '@/hooks/useReports';
import {
  readMockScenario,
  reportLayoutListingKey,
  ReportCappedError,
  type ReportColumn,
  type ReportDetailLayout,
  type ReportParamValue,
  type ReportParamValues,
  type ReportRow,
  type ReportView,
  type ReportViewConfig,
} from '@/services/reportService';
import { ConfigureSummaryDialog } from './ConfigureSummaryDialog';
import { ReportFilterBar } from './ReportFilterBar';
import { ReportPivotTable } from './ReportPivotTable';
import { ReportViewsMenu } from './ReportViewsMenu';

type PageState = {
  viewId: string | null;
  params: ReportParamValues;
  detail: ReportViewConfig['detail'];
  pivot: ReportViewConfig['pivot'];
  /** Bumped when a view is applied, so the grid drops the user's in-session columns. */
  token: number;
};

type GridState = { visibility: VisibilityState; order: string[]; token: number };

/** A saved view names the GROUP SOURCE; the run result says which tick columns it became. */
function expandDetailColumns(keys: string[], layout: ReportDetailLayout): string[] {
  return keys.flatMap((key) => {
    const group = layout.column_groups.find((g) => g.source === key);
    return group ? group.keys : [key];
  });
}

function gridStateFromView(detail: ReportViewConfig['detail'], layout: ReportDetailLayout): GridState {
  const visibleKeys = new Set(expandDetailColumns(detail.columns, layout));
  const visibility: VisibilityState = {};
  for (const column of layout.columns) visibility[column.key] = visibleKeys.has(column.key);
  const ordered = expandDetailColumns(detail.order.length ? detail.order : detail.columns, layout);
  const order = [...ordered, ...layout.columns.map((c) => c.key).filter((k) => !ordered.includes(k))];
  return { visibility, order, token: -1 };
}

function cellFor(column: ReportColumn) {
  return function Cell({ getValue }: { getValue: () => unknown }) {
    const value = getValue();
    if (column.type === 'bool') {
      return value ? <Check className="size-4 text-muted-foreground" aria-label="Yes" /> : null;
    }
    if (value == null || value === '') return <span className="text-muted-foreground">-</span>;
    if (column.type === 'money') {
      return <span className="block text-end tabular-nums">{formatMoney2dp(String(value), '-')}</span>;
    }
    if (column.type === 'date') return <span>{formatDateSafe(String(value))}</span>;
    const text = String(value);
    return (
      <span className="truncate" title={text}>
        {text}
      </span>
    );
  };
}

function buildColumns(layout: ReportDetailLayout): ColumnDef<ReportRow>[] {
  const byKey = new Map(layout.columns.map((c) => [c.key, c]));
  const grouped = new Set(layout.column_groups.flatMap((g) => g.keys));

  const leaf = (column: ReportColumn): ColumnDef<ReportRow> => ({
    accessorKey: column.key,
    id: column.key,
    header: ({ column: tableColumn }) => (
      <DataGridColumnHeader title={column.label} column={tableColumn} />
    ),
    size: column.size ?? 140,
    cell: cellFor(column),
    /**
     * The totals row. Every column declares a footer so the "Total" label can follow the
     * column the user dragged to the front: pinning it to the column that happened to be
     * first when the run came back leaves the word stranded mid-row after a reorder.
     */
    footer: ({ column: tableColumn }) => {
      if (column.type === 'money') {
        return (
          <span className="block text-end tabular-nums">
            {formatMoney2dp(layout.totals[column.key], '')}
          </span>
        );
      }
      return tableColumn.getIndex() === 0 ? 'Total' : null;
    },
    meta: { headerTitle: column.label, skeleton: <Skeleton className="h-4 w-24" /> },
  });

  const out: ColumnDef<ReportRow>[] = [];
  layout.columns.forEach((column) => {
    if (grouped.has(column.key)) {
      const group = layout.column_groups.find((g) => g.keys[0] === column.key);
      if (!group) return;
      out.push({
        id: group.source,
        header: group.label,
        columns: group.keys
          .map((key) => byKey.get(key))
          .filter((c): c is ReportColumn => Boolean(c))
          .map((c) => leaf(c)),
      });
      return;
    }
    out.push(leaf(column));
  });
  return out;
}

/**
 * The one report screen. Everything about it comes from `GET /reports/{key}` and
 * `POST /reports/{key}/run`, so report #2 is a two-line route wrapper over this file and
 * nothing here learns its name (PLAN-reporting-foundation, "Why a foundation and not a page").
 */
export function ReportPage({
  reportKey,
  breadcrumb,
}: {
  reportKey: string;
  breadcrumb: { label: string; href?: string }[];
}) {
  const searchParams = useSearchParams();
  const scenario = readMockScenario(searchParams.toString());

  const { data: meta, isLoading: metaLoading, error: metaError, refetch: refetchMeta } = useReportMeta(
    reportKey,
    scenario,
  );
  const { data: views } = useReportViews(reportKey);
  const exportMutation = useReportExport(reportKey);

  const [state, setState] = useState<PageState | null>(null);
  const [gridOverride, setGridOverride] = useState<GridState | null>(null);
  const [configureOpen, setConfigureOpen] = useState(false);
  const [activeTab, setActiveTab] = useState('detail');
  const [sorting, setSorting] = useState<SortingState>([]);
  const [pagination, setPagination] = useState<PaginationState>({ pageIndex: 0, pageSize: 25 });

  const applyView = (view: ReportView | null, fallback: ReportViewConfig) => {
    const config = view?.view ?? fallback;
    setState((prev) => ({
      viewId: view?.id ?? null,
      params: config.params,
      detail: config.detail,
      pivot: config.pivot,
      token: (prev?.token ?? 0) + 1,
    }));
    setPagination((prev) => ({ ...prev, pageIndex: 0 }));
  };

  // The report opens on the shared default view when one exists, else on the report's own
  // default. Both queries have to have answered, or a default view would be missed.
  // Both lists are searched: a published view stays under Mine for its own author, so
  // looking only at `shared` would miss the default from the account that published it.
  useEffect(() => {
    if (state || !meta || !views) return;
    const fallback = [...views.mine, ...views.shared].find((v) => v.is_default) ?? null;
    const config = fallback?.view ?? meta.default_view;
    setState({
      viewId: fallback?.id ?? null,
      params: config.params,
      detail: config.detail,
      pivot: config.pivot,
      token: 0,
    });
  }, [state, meta, views]);

  const runView: ReportViewConfig | null = useMemo(
    () =>
      state
        ? // Empty `detail.columns` asks for the whole catalog: hiding a column is then a
          // client-side tick rather than a round trip, and a hidden column stays offerable.
          { params: state.params, detail: { columns: [], order: [] }, pivot: state.pivot }
        : null,
    [state],
  );

  const {
    data: result,
    error: runError,
    isFetching,
    refetch: refetchRun,
  } = useReportRun(reportKey, state?.params ?? {}, runView, scenario);

  const detailLayout = result?.layouts.detail;
  const columns = useMemo(() => (detailLayout ? buildColumns(detailLayout) : []), [detailLayout]);
  const desiredGrid = useMemo(
    () =>
      detailLayout && state
        ? { ...gridStateFromView(state.detail, detailLayout), token: state.token }
        : null,
    [detailLayout, state],
  );
  const effectiveGrid =
    gridOverride && state && gridOverride.token === state.token ? gridOverride : desiredGrid;

  const table = useReactTable({
    data: (detailLayout?.rows ?? []) as ReportRow[],
    columns,
    getRowId: (_row, index) => String(index),
    state: {
      sorting,
      pagination,
      columnVisibility: effectiveGrid?.visibility ?? {},
      columnOrder: effectiveGrid?.order ?? [],
    },
    onSortingChange: setSorting,
    onPaginationChange: setPagination,
    onColumnVisibilityChange: (updater) =>
      setGridOverride((prev) => {
        const base = prev ?? effectiveGrid;
        if (!base || !state) return prev;
        const next = typeof updater === 'function' ? updater(base.visibility) : updater;
        return { visibility: next, order: base.order, token: state.token };
      }),
    onColumnOrderChange: (updater) =>
      setGridOverride((prev) => {
        const base = prev ?? effectiveGrid;
        if (!base || !state) return prev;
        const next = typeof updater === 'function' ? updater(base.order) : updater;
        return { visibility: base.visibility, order: next, token: state.token };
      }),
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getPaginationRowModel: getPaginationRowModel(),
  });

  /** What Save view and Export record: the columns the user can actually see, in order. */
  const visibleDetail = (): ReportViewConfig['detail'] => {
    const visible = table.getVisibleLeafColumns().map((c) => c.id);
    return { columns: visible, order: visible };
  };

  const currentConfig: ReportViewConfig | null = state
    ? { params: state.params, detail: visibleDetail(), pivot: state.pivot }
    : null;

  const setParam = (key: string, value: ReportParamValue) => {
    setState((prev) => (prev ? { ...prev, params: { ...prev.params, [key]: value } } : prev));
    setPagination((prev) => ({ ...prev, pageIndex: 0 }));
  };

  const heading = (
    <Container>
      <Toolbar>
        <ToolbarHeading>
          <ToolbarTitle>{meta?.title ?? 'Report'}</ToolbarTitle>
          <Breadcrumb>
            <BreadcrumbList>
              <BreadcrumbItem>
                <BreadcrumbLink href="/">Home</BreadcrumbLink>
              </BreadcrumbItem>
              {breadcrumb.map((crumb) => (
                <Fragment key={crumb.label}>
                  <BreadcrumbSeparator />
                  <BreadcrumbItem>
                    {crumb.href ? (
                      <BreadcrumbLink href={crumb.href}>{crumb.label}</BreadcrumbLink>
                    ) : (
                      <BreadcrumbPage>{crumb.label}</BreadcrumbPage>
                    )}
                  </BreadcrumbItem>
                </Fragment>
              ))}
            </BreadcrumbList>
          </Breadcrumb>
        </ToolbarHeading>
        <ToolbarActions>
          {meta && state && currentConfig && (
            <>
              <ReportViewsMenu
                reportKey={reportKey}
                canPublish={meta.can_publish}
                currentViewId={state.viewId}
                currentConfig={currentConfig}
                onApply={(view) => applyView(view, meta.default_view)}
              />
              <Button variant="outline" onClick={() => setConfigureOpen(true)} className="gap-1.5">
                <Settings2 className="size-4" />
                Configure summary
              </Button>
              <Button
                onClick={() =>
                  exportMutation.mutate({ params: state.params, view: currentConfig })
                }
                disabled={exportMutation.isPending}
                className="gap-1.5"
              >
                <Download className="size-4" />
                Export to Excel
              </Button>
            </>
          )}
        </ToolbarActions>
      </Toolbar>
    </Container>
  );

  if (metaError) {
    return (
      <>
        {heading}
        <Container>
          <Alert variant="destructive" appearance="light">
            <AlertTitle>{metaError.message}</AlertTitle>
            <AlertDescription>
              <Button variant="outline" size="sm" onClick={() => void refetchMeta()}>
                Try again
              </Button>
            </AlertDescription>
          </Alert>
        </Container>
      </>
    );
  }

  if (metaLoading || !meta || !state) {
    return (
      <>
        {heading}
        <Container>
          <Card>
            <CardContent className="space-y-4 py-6">
              <Skeleton className="h-9 w-full max-w-3xl" />
              <Skeleton className="h-64 w-full" />
            </CardContent>
          </Card>
        </Container>
      </>
    );
  }

  const capped = runError instanceof ReportCappedError;
  const detailTitle = detailLayout?.title ?? 'Detail';
  const summary = result?.layouts.summary;
  const moneyColumn = detailLayout?.columns.find((c) => c.type === 'money');
  const withValue =
    detailLayout && moneyColumn
      ? detailLayout.rows.filter((row) => row[moneyColumn.key] != null && row[moneyColumn.key] !== '')
          .length
      : 0;

  return (
    <>
      {heading}
      <Container>
        <div className="space-y-5">
          <Card>
            <CardContent className="py-4">
              <ReportFilterBar
                params={meta.params}
                values={state.params}
                onChange={setParam}
                disabled={isFetching}
              />
            </CardContent>
          </Card>

          {capped && (
            <Alert variant="warning" appearance="light">
              <AlertTitle>{runError.message}</AlertTitle>
              <AlertDescription>
                <Button
                  size="sm"
                  onClick={() =>
                    currentConfig &&
                    exportMutation.mutate({ params: state.params, view: currentConfig })
                  }
                  className="gap-1.5"
                >
                  <Download className="size-4" />
                  Export to Excel
                </Button>
              </AlertDescription>
            </Alert>
          )}

          {runError && !capped && (
            <Alert variant="destructive" appearance="light">
              <AlertTitle>{runError.message}</AlertTitle>
              <AlertDescription>
                <Button variant="outline" size="sm" onClick={() => void refetchRun()}>
                  Try again
                </Button>
              </AlertDescription>
            </Alert>
          )}

          {!runError && !result && (
            <Card>
              <CardContent className="space-y-3 py-6">
                <Skeleton className="h-9 w-64" />
                <Skeleton className="h-56 w-full" />
              </CardContent>
            </Card>
          )}

          {!runError && result && result.row_count === 0 && (
            <Card>
              <CardContent className="flex flex-col items-center gap-3 py-12 text-center">
                <p className="text-sm font-medium">No sponsorships in {result.period_label}</p>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => applyView(null, meta.default_view)}
                >
                  Reset to report default
                </Button>
              </CardContent>
            </Card>
          )}

          {!runError && result && result.row_count > 0 && detailLayout && summary && (
            <Tabs value={activeTab} onValueChange={setActiveTab} className="w-full">
              <TabsList className="w-full justify-start overflow-x-auto">
                <TabsTrigger value="detail">
                  {detailTitle} ({result.row_count})
                </TabsTrigger>
                <TabsTrigger value="summary">{summary.title}</TabsTrigger>
              </TabsList>

              <TabsContent value="detail" className="mt-5">
                <DataGrid
                  table={table}
                  recordCount={result.row_count}
                  isLoading={isFetching}
                  listingKey={reportLayoutListingKey(meta.permission, detailLayout.key)}
                  tableLayout={{ width: 'fixed', columnsResizable: true, columnsVisibility: true }}
                >
                  <Card>
                    <CardHeader className="block">
                      <DataGridListToolbar
                        table={table}
                        exportConfig={false}
                        onRefresh={() => void refetchRun()}
                        isRefreshing={isFetching}
                      />
                    </CardHeader>
                    <CardTable>
                      <ScrollArea>
                        <DataGridTable />
                        <ScrollBar orientation="horizontal" />
                      </ScrollArea>
                    </CardTable>
                    <CardFooter>
                      <DataGridPagination />
                    </CardFooter>
                  </Card>
                </DataGrid>
                {moneyColumn && (
                  <p className="mt-3 text-xs text-muted-foreground">
                    {withValue} of {result.row_count} rows have a {moneyColumn.label.toLowerCase()}
                  </p>
                )}
              </TabsContent>

              <TabsContent value="summary" className="mt-5">
                <ReportPivotTable layout={summary} />
              </TabsContent>
            </Tabs>
          )}
        </div>
      </Container>

      <ConfigureSummaryDialog
        open={configureOpen}
        onOpenChange={setConfigureOpen}
        catalog={meta.catalog}
        value={state.pivot}
        onApply={(pivot) => setState((prev) => (prev ? { ...prev, pivot } : prev))}
      />
    </>
  );
}
