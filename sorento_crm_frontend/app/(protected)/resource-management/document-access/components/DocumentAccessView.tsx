'use client';

import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useState,
} from 'react';
import {
  getCoreRowModel,
  useReactTable,
  type ColumnDef,
} from '@tanstack/react-table';
import { Badge } from '@/components/ui/badge';
import { Card, CardHeader, CardTable } from '@/components/ui/card';
import { Checkbox } from '@/components/ui/checkbox';
import { DataGrid } from '@/components/ui/data-grid';
import { DataGridTable } from '@/components/ui/data-grid-table';
import { Skeleton } from '@/components/ui/skeleton';
import { PageHeader } from '@/components/common/PageHeader';
import { ListSearchInput } from '@/components/common/ListSearchInput';
import {
  SearchableSelect,
  type SearchableSelectOption,
} from '@/components/common/SearchableSelect';
import { cn } from '@/lib/utils';
import { useHasPermission } from '@/hooks/usePermissions';
import {
  useDocumentAccessMutations,
  type TickInput,
  useDocumentAccessQuery,
} from '../hooks/useDocumentAccessQuery';
import { searchPreviewContacts } from '../services/documentAccessService';
import type {
  AccessTypeColumn,
  DocumentAccessRow,
  PreviewContact,
} from '../types/documentAccess.types';
import { useIsPhone } from '../hooks/useIsPhone';
import { DocumentAccessCards } from './DocumentAccessCards';
import { DocumentAccessSheet } from './DocumentAccessSheet';
import { CONTACT_COLUMN_CLASS, REACH_CLASS } from './tickStyles';
import { RowVerdictPill } from './DocumentAccessVerdict';

const AI_FILTER_OPTIONS: SearchableSelectOption[] = [
  { value: 'on', label: 'On' },
  { value: 'off', label: 'Off' },
];

/** The rows whose tick save is pending; each row's ticks are locked until that row is re-read. */
const PendingRowContext = createContext<ReadonlySet<string>>(new Set());

const isOn = (row: DocumentAccessRow) =>
  row.ai_read_staff || row.ai_read_codes.length > 0;

export function DocumentAccessView() {
  const canEdit = useHasPermission('resource.attachment_types.edit');
  const canPreview = useHasPermission('user_management.contacts.view');
  const [search, setSearch] = useState('');
  const [aiFilter, setAiFilter] = useState('');
  const [contact, setContact] = useState<SearchableSelectOption | null>(null);
  const [openId, setOpenId] = useState<string | null>(null);

  const { data, isLoading, isPlaceholderData, error, refetch } =
    useDocumentAccessQuery(contact?.value);
  const { tick } = useDocumentAccessMutations();
  const [pendingRowIds, setPendingRowIds] = useState<ReadonlySet<string>>(
    new Set(),
  );
  const tickMutateAsync = tick.mutateAsync;
  // One lock per row: a save for row B never frees row A, which stays locked until ITS save and refresh end.
  const mutateTick = useCallback(
    (input: TickInput) => {
      const id = input.row.id;
      setPendingRowIds((prev) => new Set(prev).add(id));
      tickMutateAsync(input)
        .catch(() => undefined) // the hook's onError already toasted
        .finally(() =>
          setPendingRowIds((prev) => {
            const next = new Set(prev);
            next.delete(id);
            return next;
          }),
        );
    },
    [tickMutateAsync],
  );
  const phone = useIsPhone();

  const accessTypes = useMemo(() => data?.access_types ?? [], [data]);
  const previewContact: PreviewContact | null = data?.contact ?? null;
  const catalogue = useMemo(
    () => accessTypes.map((a) => a.code),
    [accessTypes],
  );

  const rows = useMemo(() => {
    const q = search.trim().toLowerCase();
    return (data?.rows ?? [])
      .filter((r) => r.type_name.toLowerCase().includes(q))
      .filter((r) => !aiFilter || (aiFilter === 'on') === isOn(r))
      .sort(
        (a, b) =>
          b.readable_count - a.readable_count ||
          a.type_name.localeCompare(b.type_name),
      );
  }, [data, search, aiFilter]);
  const openRow = (data?.rows ?? []).find((r) => r.id === openId) ?? null;

  const columns = useMemo<ColumnDef<DocumentAccessRow>[]>(() => {
    const tickCell = (code: string | null, name: string) =>
      function TickCell({ row }: { row: { original: DocumentAccessRow } }) {
        const r = row.original;
        const on =
          code === null ? r.ai_read_staff : r.ai_read_codes.includes(code);
        const pendingIds = useContext(PendingRowContext);
        const reach = code === null ? r.readable_count : (r.reach[code] ?? 0);
        const short =
          code !== null &&
          on &&
          r.readable_count > 0 &&
          reach < r.readable_count;
        return (
          <div
            className="flex flex-col items-center gap-0.5"
            onClick={(e) => e.stopPropagation()}
          >
            <Checkbox
              size="sm"
              checked={on}
              disabled={!canEdit || pendingIds.has(r.id)}
              aria-label={`${name} reads ${r.type_name}`}
              onCheckedChange={(next) =>
                mutateTick({ row: r, code, name, on: next === true, catalogue })
              }
            />
            {short ? (
              <span
                className={REACH_CLASS}
                title={`${reach} of ${r.readable_count} documents carry ${name}`}
              >
                {`${reach}/${r.readable_count}`}
              </span>
            ) : null}
          </div>
        );
      };
    const tickColumn = (
      code: string | null,
      name: string,
      highlight: boolean,
    ): ColumnDef<DocumentAccessRow> => ({
      id: code ?? 'staff',
      header: () => (
        <span className="block whitespace-normal text-center leading-tight">
          {name}
        </span>
      ),
      size: 84,
      cell: tickCell(code, name),
      meta: {
        headerClassName: cn('text-center', highlight && CONTACT_COLUMN_CLASS),
        cellClassName: cn('text-center', highlight && CONTACT_COLUMN_CLASS),
        headerAttributes: highlight
          ? { 'data-contact-access': 'true' }
          : undefined,
        skeleton: <Skeleton className="mx-auto size-4" />,
      },
    });
    const held = new Set(
      previewContact && previewContact.runs_as === 'contact'
        ? previewContact.access_types
        : [],
    );
    return [
      {
        id: 'type',
        header: 'Type',
        size: 220,
        cell: ({ row }) => (
          <div className="min-w-0">
            <div
              className="truncate font-medium"
              title={row.original.type_name}
            >
              {row.original.type_name}
            </div>
            <div className="text-xs text-muted-foreground">
              {`${row.original.is_shared ? 'Shared · ' : ''}${row.original.file_count.toLocaleString('en-US')} files`}
            </div>
          </div>
        ),
        meta: { skeleton: <Skeleton className="h-4 w-32" /> },
      },
      {
        id: 'documents',
        header: 'Documents',
        size: 110,
        cell: ({ row }) =>
          row.original.readable_count ? (
            `${row.original.readable_count.toLocaleString('en-US')} readable`
          ) : (
            <span className="text-muted-foreground">none readable</span>
          ),
      },
      ...(previewContact
        ? [
            {
              id: 'preview',
              header: `${previewContact.name ?? 'Contact'} reads`,
              size: 250,
              cell: ({ row }: { row: { original: DocumentAccessRow } }) => (
                <RowVerdictPill
                  row={row.original}
                  contact={previewContact}
                  accessTypes={accessTypes}
                />
              ),
              meta: {
                headerClassName: 'bg-primary/5',
                cellClassName: 'bg-primary/5',
              },
            } as ColumnDef<DocumentAccessRow>,
          ]
        : []),
      tickColumn(null, 'Staff', false),
      ...accessTypes.map((a: AccessTypeColumn) =>
        tickColumn(a.code, a.name, held.has(a.code)),
      ),
      {
        id: 'sent',
        header: 'Sent as a file',
        size: 140,
        cell: ({ row }) => (
          <div className="space-y-0.5">
            {row.original.is_direct_access ? (
              <Badge variant="info" appearance="light">
                Direct access
              </Badge>
            ) : null}
            {row.original.grant_count ? (
              <div className="text-xs text-muted-foreground">{`Granted to ${row.original.grant_count}`}</div>
            ) : null}
            {!row.original.is_direct_access && !row.original.grant_count ? (
              <span className="text-muted-foreground">-</span>
            ) : null}
          </div>
        ),
      },
    ];
  }, [accessTypes, canEdit, catalogue, previewContact, mutateTick]);

  const table = useReactTable({
    data: rows,
    columns,
    getRowId: (r) => r.id,
    getCoreRowModel: getCoreRowModel(),
    columnResizeMode: 'onChange',
    state: { columnPinning: { left: ['type'] } },
  });

  const nameOf = (code: string) =>
    accessTypes.find((a) => a.code === code)?.name ?? code;

  const toolbar = (
    <>
      <div className="flex flex-wrap items-center gap-2">
        <ListSearchInput
          value={search}
          onChange={setSearch}
          placeholder="Search types..."
          className="w-full sm:w-64"
        />
        <SearchableSelect
          aria-label="AI reads"
          value={aiFilter}
          onChange={setAiFilter}
          options={AI_FILTER_OPTIONS}
          placeholder="AI reads"
          clearable
          className="w-full sm:w-36"
        />
        {canPreview ? (
          <SearchableSelect
            aria-label="Preview as"
            value={contact?.value ?? ''}
            selectedOption={contact ?? undefined}
            onOptionChange={setContact}
            onChange={() => undefined}
            fetchOptions={async (query) =>
              (await searchPreviewContacts(query)).map((c) => ({
                value: c.id,
                label: c.name,
              }))
            }
            placeholder="Preview as"
            clearable
            className="w-full sm:w-64"
          />
        ) : null}
      </div>
      {previewContact ? (
        <div className="flex flex-wrap items-center gap-x-6 gap-y-2 text-sm">
          <span className="flex items-center gap-2">
            <span className="text-muted-foreground">Runs as</span>
            <Badge
              variant={
                previewContact.runs_as === 'staff' ? 'info' : 'secondary'
              }
              appearance="light"
            >
              {previewContact.runs_as === 'staff'
                ? 'Staff user (linked)'
                : 'Contact'}
            </Badge>
          </span>
          <span className="flex items-center gap-2">
            <span className="text-muted-foreground">Agent on WhatsApp</span>
            <Badge
              variant={previewContact.agent_on ? 'success' : 'warning'}
              appearance="light"
            >
              {previewContact.agent_on ? 'On' : 'Off'}
            </Badge>
          </span>
          <span className="flex flex-wrap items-center gap-2">
            <span className="text-muted-foreground">Access types</span>
            {previewContact.access_types.length ? (
              previewContact.access_types.map((c) => (
                <Badge key={c} variant="primary" appearance="light">
                  {nameOf(c)}
                </Badge>
              ))
            ) : (
              <Badge variant="destructive" appearance="light">
                None
              </Badge>
            )}
          </span>
          <span className="flex flex-wrap items-center gap-2">
            <span className="text-muted-foreground">Companies</span>
            {previewContact.companies.length ? (
              previewContact.companies.map((c) => (
                <Badge key={c.id} variant="secondary" appearance="light">
                  {c.name}
                </Badge>
              ))
            ) : (
              <Badge variant="destructive" appearance="light">
                None
              </Badge>
            )}
          </span>
        </div>
      ) : null}
    </>
  );

  return (
    <>
      <PageHeader title="Document Access" />
      <PendingRowContext.Provider value={pendingRowIds}>
        <div className="mt-5">
          {phone ? (
            <div className="space-y-3">
              {toolbar}
              <DocumentAccessCards
                rows={rows}
                accessTypes={accessTypes}
                contact={previewContact}
                canEdit={canEdit}
                isLoading={isLoading}
                error={error}
                onRetry={() => void refetch()}
                pendingRowIds={pendingRowIds}
                onOpen={setOpenId}
                onTick={(row, code, name, on) =>
                  mutateTick({ row, code, name, on, catalogue })
                }
              />
            </div>
          ) : (
            <DataGrid
              table={table}
              recordCount={rows.length}
              isLoading={isLoading}
              isPlaceholderData={isPlaceholderData}
              error={error}
              onRetry={() => void refetch()}
              listingKey={null}
              onRowClick={(r) => setOpenId(r.id)}
              tableLayout={{
                width: 'fixed',
                columnsResizable: true,
                columnsPinnable: true,
                headerSticky: true,
              }}
              emptyMessage={
                <div>
                  <div className="font-medium">No types match</div>
                  <div className="text-sm text-muted-foreground">
                    Try another name or switch the AI reads filter.
                  </div>
                </div>
              }
            >
              <Card>
                <CardHeader className="block space-y-3">{toolbar}</CardHeader>
                <CardTable>
                  <DataGridTable />
                </CardTable>
              </Card>
            </DataGrid>
          )}
        </div>
      </PendingRowContext.Provider>
      <DocumentAccessSheet
        row={openRow}
        accessTypes={accessTypes}
        contact={previewContact}
        canEdit={canEdit}
        onClose={() => setOpenId(null)}
      />
    </>
  );
}
