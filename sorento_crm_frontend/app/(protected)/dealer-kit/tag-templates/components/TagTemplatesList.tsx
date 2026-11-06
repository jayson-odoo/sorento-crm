'use client';

/**
 * DataGrid listing of tag templates.
 *
 * Columns: name, family (badge), price type, print size (WxH mm), created_at, status, actions.
 * The standard list toolbar carries search, the Filters menu (Price type, Family, Status, all
 * multi-select, each shown as a chip) and "New Template" in one row (TAG-TEMPLATE-DUPLICATE item 5).
 * Every column sorts on the server; with no column sorted the rows are the shared manual order,
 * which a template editor reorders by dragging (item 6). The row link carries the list state so
 * the editor's prev/next walks the same rows (item 2).
 */

import { clickToken } from '@/lib/click-token';
import { useCallback, useEffect, useMemo, useState } from 'react';
import { toast } from '@/lib/toast';
import { useRouter } from 'next/navigation';
import {
  ColumnDef,
  PaginationState,
  RowSelectionState,
  getCoreRowModel,
  getPaginationRowModel,
  useReactTable,
} from '@tanstack/react-table';
import type { DragEndEvent } from '@dnd-kit/core';
import { arrayMove } from '@dnd-kit/sortable';
import type { SortingState } from '@tanstack/react-table';
import { ChevronDown, Copy, Link2, Pencil, Plus, Search, Trash2, X } from 'lucide-react';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { SearchableMultiSelect } from '@/components/common/SearchableMultiSelect';
import { joinMulti, multiValueSummary, splitMulti } from '@/lib/list-filters/multiValue';
import { buildDetailSearch } from '@/lib/listNavQuery';
import { useHasPermission } from '@/hooks/usePermissions';
import {
  DataGridTableDndRowHandle,
  DataGridTableDndRows,
} from '@/components/ui/data-grid-table-dnd-rows';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardFooter, CardHeader, CardTable } from '@/components/ui/card';
import { DataGrid } from '@/components/ui/data-grid';
import { DataGridColumnHeader } from '@/components/ui/data-grid-column-header';
import { DataGridListToolbar } from '@/components/ui/data-grid-list-toolbar';
import { buildSelectColumn, selectedRowIds } from '@/components/ui/data-grid-select-column';
import { DataGridPagination } from '@/components/ui/data-grid-pagination';
import { DataGridTable } from '@/components/ui/data-grid-table';
import { keepPreviousData, useQuery, useQueryClient } from '@tanstack/react-query';
import { ConfirmDeleteDialog } from '@/components/common/ConfirmDeleteDialog';
import { useDeferredAction } from '@/hooks/useDeferredAction';
import { useRowPending } from '@/hooks/useDeferredRowAction';
import { formatDateTimeInMalaysia } from '@/lib/helpers';
import {
  ALL_TEMPLATE_FAMILIES,
  familyLabel,
  type TagTemplate,
} from '@/lib/dealer-kit/tag-template-types';
import {
  deleteTemplate,
  duplicateTemplate,
  getTemplateUsage,
  reorderTemplates,
  type TagTemplateUsage,
} from '../../services/tagTemplateService';
import {
  fetchTagTemplateList,
  tagTemplateListKey,
  type TagTemplateFilterKey,
  type TagTemplateFilters,
} from '../lib/listQuery';
import { useSetTemplatePriceType } from '../../hooks/useSetTemplatePriceType';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import {
  TEMPLATE_PRICE_TYPE_LABEL,
  TEMPLATE_PRICE_TYPE_OPTIONS,
  type TemplatePriceType,
} from '@/lib/dealer-kit/template-price-type';
import { TagTemplateDialog } from './TagTemplateDialog';
import { AssignTemplateDialog } from './AssignTemplateDialog';
import {
  isPriceTagFamily,
  type TemplateAssignFilter,
} from '../../services/productTagTemplateService';

const PRICE_TYPE_FILTER_OPTIONS = [
  ...TEMPLATE_PRICE_TYPE_OPTIONS,
  { value: 'unset', label: 'Not set' },
];

const STATUS_FILTER_OPTIONS = [
  { value: 'live', label: 'Live' },
  { value: 'draft', label: 'Draft' },
];

/** Each filter's label and options, in the order the Filters menu and the chips show them. */
const FILTERS: { key: TagTemplateFilterKey; label: string; placeholder: string; options: { value: string; label: string }[] }[] = [
  { key: 'price_type', label: 'Price type', placeholder: 'All price types', options: PRICE_TYPE_FILTER_OPTIONS },
  { key: 'family', label: 'Family', placeholder: 'All families', options: ALL_TEMPLATE_FAMILIES },
  { key: 'status', label: 'Status', placeholder: 'All statuses', options: STATUS_FILTER_OPTIONS },
];

/** "Price type: LP, Not set" - the chip a set filter shows above the grid. */
function filterChipLabel(filter: (typeof FILTERS)[number], raw: string): string {
  const labels = splitMulti(raw).map(
    (value) => filter.options.find((o) => o.value === value)?.label ?? value,
  );
  return `${filter.label}: ${multiValueSummary(labels)}`;
}

/** The price type cell: the type as a badge, or "Set price type" while it is unset. Opens a menu to
 * change it (a template fact, so no republish). */
function PriceTypeCell({
  template,
  onChange,
}: {
  template: TagTemplate;
  onChange: (next: TemplatePriceType | null) => void;
}) {
  const current = template.price_type ?? null;
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button
          type="button"
          aria-label={`Change price type of ${template.name}`}
          onClick={(e) => e.stopPropagation()}
          className="inline-flex items-center gap-1 rounded-md focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-ring"
        >
          {current ? (
            <Badge variant="secondary" className="font-normal">
              {TEMPLATE_PRICE_TYPE_LABEL[current]}
            </Badge>
          ) : (
            <Badge variant="warning" className="font-normal">
              Set price type
            </Badge>
          )}
          <ChevronDown className="size-3 text-muted-foreground" />
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start" onClick={(e) => e.stopPropagation()}>
        {TEMPLATE_PRICE_TYPE_OPTIONS.map((option) => (
          <DropdownMenuItem key={option.value} onSelect={() => onChange(option.value)}>
            {option.label}
          </DropdownMenuItem>
        ))}
        {current ? (
          <DropdownMenuItem onSelect={() => onChange(null)}>Clear</DropdownMenuItem>
        ) : null}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

function plural(count: number, noun: string): string {
  return `${count} ${noun}${count === 1 ? '' : 's'}`;
}

/** "2 products, 1 combo and 3 requests", or null when nothing uses it. */
function usageSentence(usage: TagTemplateUsage): string | null {
  const parts = [
    usage.products ? plural(usage.products, 'product') : null,
    usage.combos ? plural(usage.combos, 'combo') : null,
    usage.requests ? plural(usage.requests, 'request') : null,
  ].filter((p): p is string => p !== null);
  if (parts.length === 0) return null;
  if (parts.length === 1) return parts[0];
  return `${parts.slice(0, -1).join(', ')} and ${parts[parts.length - 1]}`;
}

export function TagTemplatesList() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const canManage = useHasPermission('dealer_kit.tag_templates.manage');
  const [sorting, setSorting] = useState<SortingState>([]);
  const [searchQuery, setSearchQuery] = useState('');
  const [filters, setFilters] = useState<TagTemplateFilters>({});
  const setFilter = useCallback((key: TagTemplateFilterKey, value: string) => {
    setFilters((prev) => ({ ...prev, [key]: value || undefined }));
  }, []);
  const activeFilters = FILTERS.filter((f) => filters[f.key]);

  const [pagination, setPagination] = useState<PaginationState>({
    pageIndex: 0,
    pageSize: 50,
  });
  useEffect(() => {
    setPagination((prev) => ({ ...prev, pageIndex: 0 }));
  }, [searchQuery, filters]);
  const [createOpen, setCreateOpen] = useState(false);
  // PRICETAG-TEMPLATE-PER-PRODUCT: the row's "Assign to products" dialog, and
  // its Remove, which parks here (an unlink) so the countdown outlives the dialog.
  const [assignTarget, setAssignTarget] = useState<{ id: string; name: string } | null>(null);
  const [unassign, setUnassign] = useState<{
    batchId: string;
    templateId: string;
    subject: string;
    filter: TemplateAssignFilter;
  } | null>(null);
  const unassignment = useDeferredAction({
    actionKey: 'tag_template.unassign_products',
    entityType: 'tag_template',
    entityId: unassign?.templateId ?? null,
    verb: 'Removing',
    subject: unassign?.subject ?? '',
    surface: 'toast',
    successMessage: 'Template removed from products',
    payload: { ...(unassign?.filter ?? {}) },
    invalidateKeys: [['product-tag-templates'], ['tag-template-assign-preview']],
  });
  useEffect(() => {
    if (unassign) unassignment.start();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [unassign?.batchId]);
  const [rowSelection, setRowSelection] = useState<RowSelectionState>({});

  // The whole filtered, sorted list, under the key the editor's pager reads too (item 2).
  const listQuery = useMemo(
    () => ({ sorting, searchQuery, filters }),
    [sorting, searchQuery, filters],
  );
  const templatesQuery = useQuery({
    queryKey: tagTemplateListKey(listQuery),
    queryFn: () => fetchTagTemplateList(listQuery),
    placeholderData: keepPreviousData,
  });
  const templates = useMemo(() => templatesQuery.data ?? [], [templatesQuery.data]);
  const isLoading = templatesQuery.isLoading;
  const loadError = templatesQuery.data ? null : templatesQuery.error;

  const fetchData = useCallback(async () => {
    try {
      await queryClient.invalidateQueries({ queryKey: ['tag-templates', 'list'], throwOnError: true });
    } catch (e) {
      // Rows already on screen stay; the grid shows the failure only in place of no rows.
      toast.error(e instanceof Error ? e.message : 'Could not refresh the templates.');
    }
  }, [queryClient]);

  const setPriceType = useSetTemplatePriceType();
  const { mutateAsync: savePriceType } = setPriceType;
  const changePriceType = useCallback(
    async (template: TagTemplate, next: TemplatePriceType | null) => {
      try {
        await savePriceType({ id: template.id, priceType: next });
        toast.success(next ? `${template.name}: ${TEMPLATE_PRICE_TYPE_LABEL[next]}` : `${template.name}: price type cleared`);
        await fetchData();
      } catch (e) {
        toast.error(e instanceof Error ? e.message : 'Could not save the price type.');
      }
    },
    [fetchData, savePriceType],
  );

  // Delete selected (D26, S11): the backend validates and deletes the whole
  // selection ATOMICALLY (a foreign/missing id refuses everything, nothing
  // partial), so this is ONE `useDeferredAction`, not `useDeferredBulkAction`
  // (that hook parks one independent action per row - the wrong shape when a
  // single id has to be able to sink the whole batch). `bulkDelete` freezes
  // the ids AND the noun read off them at the click: the selection is cleared
  // right after (so the grid does not keep dead rows looking tickable), and the
  // toast's copy is read again when the window lapses - anything derived live
  // from the selection would say "0 templates" by then.
  const [bulkDelete, setBulkDelete] = useState<{
    batchId: string;
    ids: string[];
    noun: string;
  } | null>(null);
  const bulkDeleteNoun = bulkDelete?.noun ?? '';

  const bulkDeletion = useDeferredAction({
    actionKey: 'tag_template.bulk_delete',
    entityType: 'tag_template',
    entityId: bulkDelete?.batchId ?? null,
    verb: 'Deleting',
    subject: bulkDeleteNoun,
    surface: 'toast',
    successMessage: `${bulkDeleteNoun} deleted`,
    payload: { template_ids: bulkDelete?.ids ?? [] },
    // Every row the reader picked dims for the length of the window, even though
    // the action is keyed on the batch token: the countdown names the count, and
    // the rows show which ones it means (D26).
    dimEntityIds: bulkDelete?.ids,
    onCommitted: fetchData,
  });

  // The per-row Delete ASKS first (TAG-TEMPLATE-DELETE-CONFIRM, owner 5 Nov, an
  // explicit exception to D7 after a one-click loss on prod): the confirm names the
  // template and what uses it. The server archives, so links and versions survive.
  const [deleteTarget, setDeleteTarget] = useState<{ id: string; name: string } | null>(null);
  const usageQuery = useQuery({
    queryKey: ['tag-template-usage', deleteTarget?.id],
    queryFn: () => getTemplateUsage(deleteTarget!.id),
    enabled: deleteTarget !== null,
  });
  const usedBy = usageQuery.data ? usageSentence(usageQuery.data) : null;
  const rowPending = useRowPending<TagTemplate>('tag_template');

  // `start()` reads its OWN hook's current closure, which only carries the
  // batch above once a render has actually happened - calling it inline in
  // the click handler would still see last render's `entityId: null` and
  // no-op.
  useEffect(() => {
    if (bulkDelete) bulkDeletion.start();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [bulkDelete?.batchId]);

  // The list state rides on the editor's URL so its prev/next walks these rows (item 2). The grid
  // appends page/limit/sort/query itself (`rowHref`); the filters ride in the href's own query.
  const filterSearch = useMemo(() => {
    const params = new URLSearchParams();
    for (const f of FILTERS) {
      const value = filters[f.key];
      if (value) params.set(f.key, value);
    }
    return params.toString();
  }, [filters]);
  const rowHref = useCallback(
    (row: TagTemplate) =>
      `/dealer-kit/tag-templates/${row.id}${filterSearch ? `?${filterSearch}` : ''}`,
    [filterSearch],
  );
  /** The editor URL with the WHOLE list state, for a push that is not a row click. */
  const editorHref = useCallback(
    (id: string) => {
      const search = buildDetailSearch(
        { pageIndex: pagination.pageIndex, pageSize: pagination.pageSize, sorting, searchQuery },
        { ...filters, from: id },
      );
      return `/dealer-kit/tag-templates/${id}${search ? `?${search}` : ''}`;
    },
    [filters, pagination.pageIndex, pagination.pageSize, searchQuery, sorting],
  );

  // Duplicate (TAG-TEMPLATE-DUPLICATE): the copy is a new draft right below its source; it opens
  // in the editor at once, the same place a row click goes.
  const [duplicatingId, setDuplicatingId] = useState<string | null>(null);
  const handleDuplicate = useCallback(
    async (template: TagTemplate) => {
      setDuplicatingId(template.id);
      try {
        const copy = await duplicateTemplate(template.id);
        toast.success(`Duplicated as ${copy.name}`);
        await queryClient.invalidateQueries({ queryKey: ['tag-templates', 'list'] });
        router.push(editorHref(copy.id));
      } catch (e) {
        toast.error(e instanceof Error ? e.message : 'Could not duplicate the template.');
      } finally {
        setDuplicatingId(null);
      }
    },
    [editorHref, queryClient, router],
  );

  // A drop saves at once (the SO lines pattern): the rows move on screen first, the server is
  // told the new order of the rows on this page, and a failure puts the server's order back.
  const handleRowDragEnd = useCallback(
    (event: DragEndEvent) => {
      const { active, over } = event;
      if (!over || active.id === over.id) return;
      const start = pagination.pageIndex * pagination.pageSize;
      const pageRows = templates.slice(start, start + pagination.pageSize);
      const ids = pageRows.map((row) => row.id);
      const oldIndex = ids.indexOf(String(active.id));
      const newIndex = ids.indexOf(String(over.id));
      if (oldIndex === -1 || newIndex === -1) return;
      const nextIds = arrayMove(ids, oldIndex, newIndex);
      const byId = new Map(pageRows.map((row) => [row.id, row]));
      const key = tagTemplateListKey(listQuery);
      queryClient.setQueryData<TagTemplate[]>(key, (prev) =>
        prev
          ? [
              ...prev.slice(0, start),
              ...nextIds.map((id) => byId.get(id)!),
              ...prev.slice(start + pageRows.length),
            ]
          : prev,
      );
      reorderTemplates(nextIds)
        .catch((e) => toast.error(e instanceof Error ? e.message : 'Could not save the order.'))
        .finally(() => void queryClient.invalidateQueries({ queryKey: ['tag-templates', 'list'] }));
    },
    [listQuery, pagination.pageIndex, pagination.pageSize, queryClient, templates],
  );

  const columns = useMemo<ColumnDef<TagTemplate>[]>(
    () => [
      buildSelectColumn<TagTemplate>({
        rowLabel: (row) => `Select ${row.original.name}`,
      }),
      {
        accessorKey: 'name',
        header: ({ column }) => (
          <DataGridColumnHeader column={column} title="Name" />
        ),
        size: 250,
        cell: ({ row }) => (
          <span className="truncate font-medium" title={row.original.name}>
            {row.original.name}
          </span>
        ),
      },
      {
        accessorKey: 'family',
        header: ({ column }) => (
          <DataGridColumnHeader column={column} title="Family" />
        ),
        size: 150,
        cell: ({ row }) => (
          <Badge variant="secondary" className="font-normal">
            {familyLabel(row.original.family)}
          </Badge>
        ),
      },
      {
        id: 'price_type',
        header: ({ column }) => <DataGridColumnHeader column={column} title="Price type" />,
        size: 140,
        cell: ({ row }) => (
          <PriceTypeCell
            template={row.original}
            onChange={(next) => void changePriceType(row.original, next)}
          />
        ),
      },
      {
        id: 'print_size',
        header: ({ column }) => <DataGridColumnHeader column={column} title="Print Size" />,
        size: 120,
        cell: ({ row }) => {
          const ps = row.original.print_size;
          return (
            <span className="text-muted-foreground">
              {ps.width_mm} x {ps.height_mm} mm
            </span>
          );
        },
      },
      {
        accessorKey: 'created_at',
        header: ({ column }) => (
          <DataGridColumnHeader column={column} title="Created" />
        ),
        size: 160,
        cell: ({ row }) => (
          <span className="text-muted-foreground">
            {formatDateTimeInMalaysia(row.original.created_at)}
          </span>
        ),
      },
      {
        id: 'published',
        header: ({ column }) => <DataGridColumnHeader column={column} title="Status" />,
        size: 100,
        cell: ({ row }) =>
          row.original.published_version_id ? (
            <Badge variant="success" className="font-normal">
              Live v{row.original.published_version_no}
            </Badge>
          ) : (
            <Badge variant="outline" className="font-normal">
              Draft
            </Badge>
          ),
      },
      {
        id: 'actions',
        header: '',
        enableSorting: false,
        size: 130,
        cell: ({ row }) => (
          <div className="flex items-center gap-1">
            <Button
              variant="ghost"
              size="sm"
              className="h-7 w-7 p-0"
              onClick={(e) => {
                e.stopPropagation();
                router.push(editorHref(row.original.id));
              }}
              title="Edit template"
            >
              <Pencil className="size-3.5" />
            </Button>
            {canManage ? (
              <Button
                variant="ghost"
                size="sm"
                className="h-7 w-7 p-0"
                disabled={duplicatingId !== null}
                onClick={(e) => {
                  e.stopPropagation();
                  void handleDuplicate(row.original);
                }}
                title="Duplicate template"
                aria-label="Duplicate template"
              >
                <Copy className="size-3.5" />
              </Button>
            ) : null}
            {isPriceTagFamily(row.original.family) ? (
              <Button
                variant="ghost"
                size="sm"
                className="h-7 w-7 p-0"
                onClick={(e) => {
                  e.stopPropagation();
                  setAssignTarget({ id: row.original.id, name: row.original.name });
                }}
                title="Assign to products"
                aria-label="Assign to products"
              >
                <Link2 className="size-3.5" />
              </Button>
            ) : null}
            <Button
              variant="ghost"
              size="sm"
              className="h-7 w-7 p-0 text-destructive hover:text-destructive"
              onClick={(e) => {
                e.stopPropagation();
                setDeleteTarget({ id: row.original.id, name: row.original.name });
              }}
              title="Delete template"
              aria-label="Delete template"
            >
              <Trash2 className="size-3.5" />
            </Button>
          </div>
        ),
      },
    ],
    [router, changePriceType, canManage, duplicatingId, handleDuplicate, editorHref],
  );

  // Drag reorder (item 6): only in the manual order (no column sorted) and only for a user who
  // can edit templates. The handle column is the FIRST one, the same as the SO lines table.
  const reorderable = canManage && sorting.length === 0;
  const tableColumns = useMemo<ColumnDef<TagTemplate>[]>(
    () =>
      reorderable
        ? [
            {
              id: 'drag_handle',
              header: () => <span className="sr-only">Reorder</span>,
              cell: ({ row }) => <DataGridTableDndRowHandle rowId={row.original.id} />,
              size: 44,
              minSize: 44,
              enableResizing: false,
              enableSorting: false,
              meta: { headerTitle: 'Reorder' },
            },
            ...columns,
          ]
        : columns,
    [columns, reorderable],
  );

  const table = useReactTable({
    data: templates,
    columns: tableColumns,
    getRowId: (row) => row.id,
    state: { pagination, rowSelection, sorting },
    onPaginationChange: setPagination,
    onRowSelectionChange: setRowSelection,
    onSortingChange: setSorting,
    manualSorting: true,
    getCoreRowModel: getCoreRowModel(),
    getPaginationRowModel: getPaginationRowModel(),
    columnResizeMode: 'onChange',
    enableRowSelection: true,
  });

  const handleBulkDelete = () => {
    const ids = selectedRowIds(table);
    if (ids.length === 0) return;
    // The noun is frozen HERE, off the ids this click captured: the selection is
    // cleared on the next line, and the toast's own copy is read again when the
    // window lapses - live state would have it saying "0 templates" by then.
    setBulkDelete({
      batchId: clickToken(),
      ids,
      noun: `${ids.length} template${ids.length === 1 ? '' : 's'}`,
    });
    setRowSelection({});
  };

  const listPrimaryAction = (
    <Button size="sm" onClick={() => setCreateOpen(true)}>
      <Plus className="mr-1.5 size-3.5" />
      New Template
    </Button>
  );

  return (
    <>
      <Card>
        <CardHeader className="block">
          <DataGridListToolbar
            table={table}
            showColumns={false}
            exportConfig={false}
            primaryAction={listPrimaryAction}
            searchSlot={
              <div className="relative">
                <Search className="size-4 text-muted-foreground absolute start-3 top-1/2 -translate-y-1/2" />
                <Input
                  placeholder="Search templates..."
                  aria-label="Search templates"
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  className="ps-9 w-full sm:w-64"
                />
                {searchQuery && (
                  <Button
                    mode="icon"
                    variant="dim"
                    aria-label="Clear search"
                    title="Clear search"
                    className="absolute end-1.5 top-1/2 -translate-y-1/2 h-6 w-6"
                    onClick={() => setSearchQuery('')}
                  >
                    <X />
                  </Button>
                )}
              </div>
            }
            filters={{
              kind: 'custom',
              active: activeFilters.length > 0,
              activeCount: activeFilters.length,
              activeSummary: activeFilters.map((f) => ({
                label: filterChipLabel(f, filters[f.key] ?? ''),
                onClear: () => setFilter(f.key, ''),
              })),
              content: (
                <div className="space-y-4">
                  {FILTERS.map((f) => (
                    <div key={f.key}>
                      <Label>{f.label}</Label>
                      <SearchableMultiSelect
                        aria-label={f.label}
                        value={splitMulti(filters[f.key])}
                        onChange={(v) => setFilter(f.key, joinMulti(v))}
                        options={f.options}
                        placeholder={f.placeholder}
                        triggerClassName="mt-1"
                        clearable
                      />
                    </div>
                  ))}
                  {activeFilters.length > 0 && (
                    <div className="flex justify-end">
                      <Button variant="ghost" size="sm" onClick={() => setFilters({})}>
                        Clear filters
                      </Button>
                    </div>
                  )}
                </div>
              ),
            }}
            bulkActions={[
              {
                key: 'delete',
                label: 'Delete',
                icon: Trash2,
                destructive: true,
                onClick: handleBulkDelete,
              },
            ]}
          />
        </CardHeader>
        <CardTable>
          <DataGrid
            table={table}
            recordCount={templates.length}
            isLoading={isLoading}
            error={loadError}
            onRetry={() => void fetchData()}
            tableLayout={{ width: 'fixed', columnsResizable: true }}
            rowPending={rowPending}
            rowHref={rowHref}
          >
            {canManage && sorting.length > 0 ? (
              <div className="flex items-center gap-2 border-b px-4 py-2 text-xs text-muted-foreground">
                Clear sort to reorder
                <Button variant="ghost" size="sm" className="h-6 px-2" onClick={() => setSorting([])}>
                  Clear sort
                </Button>
              </div>
            ) : null}
            {reorderable ? (
              <DataGridTableDndRows
                handleDragEnd={handleRowDragEnd}
                dataIds={table.getRowModel().rows.map((row) => row.id)}
              />
            ) : (
              <DataGridTable />
            )}
            <CardFooter className="justify-center">
              <DataGridPagination />
            </CardFooter>
          </DataGrid>
        </CardTable>
      </Card>

      <ConfirmDeleteDialog
        open={deleteTarget !== null}
        onOpenChange={(open) => {
          if (!open) setDeleteTarget(null);
        }}
        title="Delete template?"
        description={
          <>
            <span className="font-medium">{deleteTarget?.name}</span>
            {usageQuery.isLoading
              ? ' - checking what uses it.'
              : usageQuery.isError
                ? ' - could not check what uses it.'
                : usedBy
                ? ` is used by ${usedBy}.`
                : ' is not used by any product, combo or request.'}
          </>
        }
        onDelete={async () => {
          if (deleteTarget) await deleteTemplate(deleteTarget.id);
        }}
        successMessage="Template deleted"
        onSuccess={() => void fetchData()}
      />
      <TagTemplateDialog
        open={createOpen}
        onOpenChange={setCreateOpen}
        onCreated={fetchData}
      />
      <AssignTemplateDialog
        template={assignTarget}
        onClose={() => setAssignTarget(null)}
        onRemove={(filter, count) => {
          if (!assignTarget) return;
          setUnassign({
            batchId: clickToken(),
            templateId: assignTarget.id,
            subject: `${assignTarget.name} from ${count} ${count === 1 ? 'product' : 'products'}`,
            filter,
          });
        }}
      />
    </>
  );
}
