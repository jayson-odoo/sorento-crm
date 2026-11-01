'use client';

import { useCallback, useMemo, useState } from 'react';
import {
  getCoreRowModel,
  useReactTable,
  type ColumnDef,
} from '@tanstack/react-table';
import { Badge } from '@/components/ui/badge';
import { DataGrid } from '@/components/ui/data-grid';
import { DataGridPagination } from '@/components/ui/data-grid-pagination';
import { DataGridTable } from '@/components/ui/data-grid-table';
import {
  Sheet,
  SheetBody,
  SheetContent,
  SheetHeader,
  SheetTitle,
} from '@/components/ui/sheet';
import { Switch } from '@/components/ui/switch';
import { Skeleton } from '@/components/ui/skeleton';
import { cn } from '@/lib/utils';
import {
  COARSE_HIT_TARGET_CLASS,
  PRESSED_CLASS,
} from '@/components/ui/primitive-classes';
import { CONTACT_COLUMN_CLASS } from './tickStyles';
import { AccessLevelsMultiSelect } from '../../attachments/components/AccessLevelsMultiSelect';
import {
  useDocumentAccessDocuments,
  useDocumentAccessMutations,
} from '../hooks/useDocumentAccessQuery';
import type {
  AccessTypeColumn,
  DocumentAccessDocument,
  DocumentAccessRow,
  PreviewContact,
} from '../types/documentAccess.types';
import { DocumentVerdictPill } from './DocumentAccessVerdict';

const PAGE_SIZE = 50;

interface Props {
  row: DocumentAccessRow | null;
  accessTypes: AccessTypeColumn[];
  contact: PreviewContact | null;
  canEdit: boolean;
  onClose: () => void;
}

export function DocumentAccessSheet({
  row,
  accessTypes,
  contact,
  canEdit,
  onClose,
}: Props) {
  return (
    <Sheet open={row !== null} onOpenChange={(open) => !open && onClose()}>
      <SheetContent side="right" className="w-full gap-0 p-0 sm:max-w-2xl">
        {row ? (
          <SheetBodyFor
            row={row}
            accessTypes={accessTypes}
            contact={contact}
            canEdit={canEdit}
          />
        ) : null}
      </SheetContent>
    </Sheet>
  );
}

function SheetBodyFor({
  row,
  accessTypes,
  contact,
  canEdit,
}: {
  row: DocumentAccessRow;
  accessTypes: AccessTypeColumn[];
  contact: PreviewContact | null;
  canEdit: boolean;
}) {
  const [page, setPage] = useState(1);
  const { tick, direct, levels } = useDocumentAccessMutations();
  const docs = useDocumentAccessDocuments(row.id, contact?.id, page, PAGE_SIZE);
  const mutateLevels = levels.mutate;
  const levelNames = useCallback(
    (codes: string[]) =>
      codes
        .map((c) => accessTypes.find((a) => a.code === c)?.name ?? c)
        .join(', '),
    [accessTypes],
  );
  const catalogue = accessTypes.map((a) => a.code);
  const held = new Set(
    contact && contact.runs_as === 'contact' ? contact.access_types : [],
  );
  const total = docs.data?.total ?? 0;
  const pages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  const chips = [
    { code: null as string | null, name: 'Staff', on: row.ai_read_staff },
    ...accessTypes.map((a) => ({
      code: a.code as string | null,
      name: a.name,
      on: row.ai_read_codes.includes(a.code),
    })),
  ];

  const columns = useMemo<ColumnDef<DocumentAccessDocument>[]>(
    () => [
      {
        id: 'file',
        header: 'File',
        size: 200,
        cell: ({ row: r }) => (
          <span className="block truncate" title={r.original.original_filename}>
            {r.original.original_filename}
          </span>
        ),
        meta: { skeleton: <Skeleton className="h-4 w-32" /> },
      },
      {
        id: 'levels',
        header: 'Access levels',
        size: 220,
        cell: ({ row: r }) =>
          canEdit && r.original.can_edit_levels ? (
            <AccessLevelsMultiSelect
              options={accessTypes}
              value={r.original.access_levels}
              onChange={(next) =>
                mutateLevels({ id: r.original.id, accessLevels: next })
              }
            />
          ) : (
            <span
              className="block truncate"
              title={levelNames(r.original.access_levels)}
            >
              {levelNames(r.original.access_levels)}
            </span>
          ),
      },
      {
        id: 'company',
        header: 'Company',
        size: 110,
        cell: ({ row: r }) =>
          r.original.company_name ? (
            <span className="block truncate" title={r.original.company_name}>
              {r.original.company_name}
            </span>
          ) : (
            <span className="text-muted-foreground">Shared</span>
          ),
      },
      ...(contact
        ? [
            {
              id: 'verdict',
              header: contact.name ?? 'Contact',
              size: 190,
              cell: ({
                row: r,
              }: {
                row: { original: DocumentAccessDocument };
              }) => <DocumentVerdictPill doc={r.original} />,
            } as ColumnDef<DocumentAccessDocument>,
          ]
        : []),
    ],
    [accessTypes, canEdit, contact, mutateLevels, levelNames],
  );

  const table = useReactTable({
    data: docs.data?.items ?? [],
    columns,
    getRowId: (d) => d.id,
    getCoreRowModel: getCoreRowModel(),
    columnResizeMode: 'onChange',
    manualPagination: true,
    pageCount: pages,
    state: { pagination: { pageIndex: page - 1, pageSize: PAGE_SIZE } },
    onPaginationChange: (updater) => {
      const next =
        typeof updater === 'function'
          ? updater({ pageIndex: page - 1, pageSize: PAGE_SIZE })
          : updater;
      setPage(next.pageIndex + 1);
    },
  });

  return (
    <>
      <SheetHeader className="border-b px-5 py-4">
        <div className="flex flex-wrap items-center gap-2 pe-8">
          <SheetTitle>{row.type_name}</SheetTitle>
          {row.is_shared ? (
            <Badge variant="secondary" appearance="light">
              Shared
            </Badge>
          ) : null}
        </div>
        <div className="text-sm text-muted-foreground">
          {`${row.file_count.toLocaleString('en-US')} files · ${row.readable_count.toLocaleString('en-US')} readable`}
        </div>
      </SheetHeader>
      <SheetBody className="space-y-6 px-5 py-4">
        <section className="space-y-2">
          <h3 className="text-sm font-semibold">Who can read</h3>
          <div className="flex flex-wrap gap-2">
            {chips.map((chip) => (
              <button
                key={chip.code ?? 'staff'}
                type="button"
                role="checkbox"
                aria-checked={chip.on}
                disabled={!canEdit || tick.isPending}
                onClick={() =>
                  tick.mutate({
                    row,
                    code: chip.code,
                    name: chip.name,
                    on: !chip.on,
                    catalogue,
                  })
                }
                className={cn(
                  'inline-flex h-8 items-center gap-2 rounded-full border px-3 text-sm disabled:cursor-not-allowed disabled:opacity-60',
                  PRESSED_CLASS,
                  COARSE_HIT_TARGET_CLASS,
                  chip.on ? 'border-primary bg-primary/10' : 'border-border',
                  chip.code &&
                    held.has(chip.code) &&
                    cn('ring-1 ring-primary', CONTACT_COLUMN_CLASS),
                )}
              >
                <span
                  aria-hidden
                  className={cn(
                    'size-3 rounded-sm border',
                    chip.on ? 'border-primary bg-primary' : 'border-input',
                  )}
                />
                <span>{chip.name}</span>
              </button>
            ))}
          </div>
        </section>

        <section className="space-y-2">
          <h3 className="text-sm font-semibold">Documents</h3>
          <DataGrid
            table={table}
            recordCount={total}
            isLoading={docs.isLoading}
            isPlaceholderData={docs.isPlaceholderData}
            error={docs.error}
            onRetry={() => void docs.refetch()}
            listingKey={null}
            tableLayout={{
              width: 'fixed',
              columnsResizable: true,
              dense: true,
            }}
            emptyMessage={
              <div>
                <div className="font-medium">No documents</div>
                <div className="text-sm text-muted-foreground">
                  Nothing readable is filed under this type.
                </div>
              </div>
            }
          >
            <DataGridTable />
            {pages > 1 ? (
              <DataGridPagination sizes={[PAGE_SIZE]} sizesInfo="" />
            ) : null}
          </DataGrid>
        </section>

        <section className="space-y-2">
          <h3 className="text-sm font-semibold">Sent as a file</h3>
          <div className="flex items-center justify-between gap-4">
            <label htmlFor="direct-access-switch" className="text-sm">
              Direct access
            </label>
            <Switch
              id="direct-access-switch"
              checked={row.is_direct_access}
              disabled={!canEdit || direct.isPending}
              onCheckedChange={(on) => direct.mutate({ row, on })}
            />
          </div>
          <div className="text-sm text-muted-foreground">
            {row.grant_count
              ? `Granted to ${row.grant_count} contact${row.grant_count === 1 ? '' : 's'}`
              : 'Granted to no contacts'}
          </div>
        </section>
      </SheetBody>
    </>
  );
}
