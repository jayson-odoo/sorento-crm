'use client';

import { useMemo, useState } from 'react';
import {
  Column,
  ColumnDef,
  getCoreRowModel,
  PaginationState,
  SortingState,
  useReactTable,
} from '@tanstack/react-table';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardFooter, CardTable } from '@/components/ui/card';
import { Checkbox } from '@/components/ui/checkbox';
import { DataGrid } from '@/components/ui/data-grid';
import { DataGridColumnHeader } from '@/components/ui/data-grid-column-header';
import { DataGridPagination } from '@/components/ui/data-grid-pagination';
import { DataGridTable } from '@/components/ui/data-grid-table';
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group';
import { SearchableSelect } from '@/components/common/SearchableSelect';
import { getProductsForLineSelect } from '../../../services/productService';
import {
  useCatalogPhotoMutations,
  useCatalogPhotosQuery,
} from '../../../hooks/useCatalogPhotoReadings';
import type {
  CatalogPhoto,
  CatalogPhotoConfidence,
  CatalogPhotoDecision,
  CatalogPhotoTab,
} from '../../../services/catalogPhotoReadingService';

const CONFIDENCE: Record<
  CatalogPhotoConfidence,
  { label: string; variant: 'success' | 'warning' | 'secondary' }
> = {
  high: { label: 'High', variant: 'success' },
  medium: { label: 'Medium', variant: 'warning' },
  low: { label: 'Low', variant: 'secondary' },
  none: { label: 'None', variant: 'secondary' },
};

const EMPTY: Record<CatalogPhotoTab, { title: string; hint: string }> = {
  ready: { title: 'No photos are ready', hint: 'Photos with a matched product appear here.' },
  duplicate: {
    title: 'No look-alikes',
    hint: 'Photos close to one already on a product appear here.',
  },
  needs_product: { title: 'Every photo has a product', hint: 'Photos without a match appear here.' },
  skipped: { title: 'Nothing skipped', hint: 'Photos you skip will appear here.' },
};

async function fetchProductOptions(query: string) {
  const rows = await getProductsForLineSelect(query);
  return rows.map((product) => ({
    value: product.id,
    label: product.product_code,
    description: product.product_name ?? undefined,
    searchText: `${product.product_code} ${product.product_name ?? ''}`,
  }));
}

function SortHeader({ title, column }: { title: string; column: Column<CatalogPhoto> }) {
  return <DataGridColumnHeader title={title} column={column} />;
}

function sortHeader(title: string): ColumnDef<CatalogPhoto>['header'] {
  const render: ColumnDef<CatalogPhoto>['header'] = ({ column }) => (
    <SortHeader title={title} column={column} />
  );
  return render;
}

function Thumb({ src, alt }: { src: string; alt: string }) {
  return (
    <img src={src} alt={alt} className="h-10 w-14 rounded border border-border object-cover" />
  );
}

function CodeCell({ row }: { row: CatalogPhoto }) {
  const text = row.printed_code ?? 'No code found';
  return (
    <span
      className={`block truncate ${row.printed_code ? 'font-medium' : 'text-muted-foreground'}`}
      title={text}
    >
      {text}
    </span>
  );
}

export function CataloguePhotosGrid({
  readingId,
  tab,
  locked,
}: {
  readingId: string;
  tab: CatalogPhotoTab;
  /** The reading is not finished yet, so nothing on it can be changed. */
  locked: boolean;
}) {
  const [sorting, setSorting] = useState<SortingState>([]);
  const [pagination, setPagination] = useState<PaginationState>({ pageIndex: 0, pageSize: 25 });
  const list = useCatalogPhotosQuery(readingId, {
    tab,
    pageIndex: pagination.pageIndex,
    pageSize: pagination.pageSize,
    sort: sorting[0]?.id,
    desc: sorting[0]?.desc,
  });
  const { patch } = useCatalogPhotoMutations(readingId);
  const rows = useMemo(() => list.data?.data ?? [], [list.data]);
  const total = list.data?.pagination.total ?? 0;

  const columns = useMemo<ColumnDef<CatalogPhoto>[]>(() => {
    const busy = patch.isPending || locked;
    const header = sortHeader;

    const thumbnail: ColumnDef<CatalogPhoto> = {
      id: 'thumbnail',
      header: 'Photo',
      size: 90,
      enableSorting: false,
      meta: { headerTitle: 'Photo' },
      cell: ({ row }) => <Thumb src={row.original.thumbnail_url} alt={`Page ${row.original.page}`} />,
    };
    const page: ColumnDef<CatalogPhoto> = {
      id: 'page',
      accessorKey: 'page',
      header: header('Page'),
      size: 80,
      meta: { headerTitle: 'Page' },
      cell: ({ row }) => <span className="tabular-nums">{row.original.page}</span>,
    };
    const code: ColumnDef<CatalogPhoto> = {
      id: 'printed_code',
      accessorKey: 'printed_code',
      header: header('Printed code'),
      size: 200,
      meta: { headerTitle: 'Printed code' },
      cell: ({ row }) => <CodeCell row={row.original} />,
    };
    const picker: ColumnDef<CatalogPhoto> = {
      id: 'product_code',
      header: header('Product'),
      size: 240,
      meta: { headerTitle: 'Product' },
      cell: ({ row }) => {
        const item = row.original;
        return (
          <SearchableSelect
            value={item.product?.id ?? ''}
            onChange={(value) => patch.mutate({ photoId: item.id, product_id: value || null })}
            fetchOptions={fetchProductOptions}
            selectedOption={
              item.product
                ? { value: item.product.id, label: item.product.product_code }
                : undefined
            }
            placeholder="Choose a product"
            clearable
            size="sm"
            truncateTriggerLabel
            disabled={busy || Boolean(item.attached_at)}
            aria-label="Product"
          />
        );
      },
    };
    const productText: ColumnDef<CatalogPhoto> = {
      id: 'product_code',
      header: header('Product'),
      size: 200,
      meta: { headerTitle: 'Product' },
      cell: ({ row }) => {
        const text = row.original.product?.product_code ?? '-';
        return (
          <span className="block truncate" title={text}>
            {text}
          </span>
        );
      },
    };
    const confidence: ColumnDef<CatalogPhoto> = {
      id: 'confidence',
      accessorKey: 'confidence',
      header: header('Confidence'),
      size: 110,
      meta: { headerTitle: 'Confidence' },
      cell: ({ row }) => {
        const entry = CONFIDENCE[row.original.confidence];
        return (
          <Badge variant={entry.variant} appearance="light" size="sm">
            {entry.label}
          </Badge>
        );
      },
    };
    const alsoAttach: ColumnDef<CatalogPhoto> = {
      id: 'also_attach',
      header: 'Also attach',
      size: 220,
      enableSorting: false,
      meta: { headerTitle: 'Also attach' },
      cell: ({ row }) => {
        const item = row.original;
        if (item.other_block_products.length === 0 && item.placeholders.length === 0) {
          return <span className="text-muted-foreground">-</span>;
        }
        return (
          <div className="flex flex-col gap-1">
            {item.other_block_products.map((other) => {
              const checked = item.also_attach_product_ids.includes(other.id);
              return (
                <label key={other.id} className="flex items-center gap-2 text-sm">
                  <Checkbox
                    size="sm"
                    checked={checked}
                    disabled={busy || Boolean(item.attached_at)}
                    onCheckedChange={(next) =>
                      patch.mutate({
                        photoId: item.id,
                        also_attach_product_ids: next
                          ? [...item.also_attach_product_ids, other.id]
                          : item.also_attach_product_ids.filter((id) => id !== other.id),
                      })
                    }
                  />
                  <span className="truncate" title={other.product_code}>
                    {other.product_code}
                  </span>
                </label>
              );
            })}
            {item.placeholders.map((placeholder) => (
              <span key={placeholder} className="flex items-center gap-2 text-xs">
                <span className="truncate text-muted-foreground line-through" title={placeholder}>
                  {placeholder}
                </span>
                <Badge variant="outline" size="sm">
                  Placeholder
                </Badge>
              </span>
            ))}
          </div>
        );
      },
    };
    const suggestion: ColumnDef<CatalogPhoto> = {
      id: 'suggestion',
      header: 'Did you mean',
      size: 170,
      enableSorting: false,
      meta: { headerTitle: 'Did you mean' },
      cell: ({ row }) =>
        row.original.suggestion ? (
          <Badge variant="outline" size="sm" title={row.original.suggestion}>
            <span className="block truncate">{row.original.suggestion}</span>
          </Badge>
        ) : (
          <span className="text-muted-foreground">-</span>
        ),
    };
    const lookAlike: ColumnDef<CatalogPhoto> = {
      id: 'compare',
      header: 'Catalogue and on file',
      size: 190,
      enableSorting: false,
      meta: { headerTitle: 'Catalogue and on file' },
      cell: ({ row }) => (
        <div className="flex items-center gap-2">
          <Thumb src={row.original.thumbnail_url} alt="From catalogue" />
          {row.original.duplicate ? (
            <Thumb src={row.original.duplicate.thumbnail_url} alt="On file now" />
          ) : null}
        </div>
      ),
    };
    const choice: ColumnDef<CatalogPhoto> = {
      id: 'decision',
      header: 'Choice',
      size: 270,
      enableSorting: false,
      meta: { headerTitle: 'Choice' },
      cell: ({ row }) => {
        const item = row.original;
        return (
          <ToggleGroup
            type="single"
            variant="outline"
            size="sm"
            value={item.decision === 'attach' ? 'skip' : item.decision}
            disabled={busy || Boolean(item.attached_at)}
            onValueChange={(next) => {
              if (next) patch.mutate({ photoId: item.id, decision: next as CatalogPhotoDecision });
            }}
            aria-label="Choice"
          >
            <ToggleGroupItem value="skip">Skip</ToggleGroupItem>
            <ToggleGroupItem value="keep_both">Keep both</ToggleGroupItem>
            <ToggleGroupItem value="replace">Replace</ToggleGroupItem>
          </ToggleGroup>
        );
      },
    };
    const action = (label: string, decision: CatalogPhotoDecision): ColumnDef<CatalogPhoto> => ({
      id: 'action',
      header: '',
      size: 110,
      enableSorting: false,
      enableResizing: false,
      meta: { headerTitle: label },
      cell: ({ row }) =>
        row.original.attached_at ? (
          <Badge variant="success" appearance="light" size="sm">
            Attached
          </Badge>
        ) : (
          <Button
            variant="outline"
            size="sm"
            disabled={busy}
            onClick={() => patch.mutate({ photoId: row.original.id, decision })}
          >
            {label}
          </Button>
        ),
    });

    switch (tab) {
      case 'ready':
        return [thumbnail, page, code, picker, confidence, alsoAttach, action('Skip', 'skip')];
      case 'duplicate':
        return [lookAlike, page, code, productText, choice];
      case 'needs_product':
        return [thumbnail, page, code, suggestion, picker, action('Skip', 'skip')];
      default:
        return [thumbnail, page, code, productText, action('Restore', 'attach')];
    }
  }, [tab, patch, locked]);

  const table = useReactTable({
    data: rows,
    columns,
    getRowId: (row) => row.id,
    state: { pagination, sorting },
    onPaginationChange: setPagination,
    onSortingChange: (updater) => {
      setSorting(updater);
      setPagination((current) => ({ ...current, pageIndex: 0 }));
    },
    pageCount: Math.max(1, Math.ceil(total / pagination.pageSize)),
    manualPagination: true,
    manualSorting: true,
    getCoreRowModel: getCoreRowModel(),
    columnResizeMode: 'onChange',
  });

  const empty = EMPTY[tab];

  return (
    <DataGrid
      table={table}
      recordCount={total}
      isLoading={list.isLoading}
      isPlaceholderData={list.isPlaceholderData}
      listingKey={null}
      tableLayout={{ width: 'fixed', columnsResizable: true }}
      emptyMessage={
        <div className="px-6 py-10 text-center">
          <h3 className="text-sm font-semibold">{empty.title}</h3>
          <p className="mx-auto mt-1 max-w-md text-sm text-muted-foreground">{empty.hint}</p>
        </div>
      }
    >
      <Card>
        <CardTable>
          <DataGridTable />
        </CardTable>
        <CardFooter>
          <DataGridPagination />
        </CardFooter>
      </Card>
    </DataGrid>
  );
}
