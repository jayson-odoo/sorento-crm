'use client';

import * as React from 'react';
import { useRouter } from 'next/navigation';
import type { ColumnDef } from '@tanstack/react-table';
import { FileDown, Plus } from 'lucide-react';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  ContextMenu,
  ContextMenuContent,
  ContextMenuItem,
  ContextMenuTrigger,
} from '@/components/ui/context-menu';
import { DataGridColumnHeader } from '@/components/ui/data-grid-column-header';
import { DataGridListToolbar } from '@/components/ui/data-grid-list-toolbar';
import { Label } from '@/components/ui/label';
import { ListSearchInput } from '@/components/common/ListSearchInput';
import { PanelDataGrid } from '@/components/common/PanelDataGrid';
import { SearchableMultiSelect } from '@/components/common/SearchableMultiSelect';
import { useDeferredRowAction } from '@/hooks/useDeferredRowAction';
import { formatDateInMalaysia } from '@/lib/helpers';
import { multiChipLabel } from '@/lib/list-filters/multiValue';
import { toast } from '@/lib/toast';

import {
  quotationCertificatesKey,
  useQuotationCertificateMutations,
  useQuotationCertificates,
} from '../../../../_shared/hooks/useQuotationCertificates';
import {
  fetchQuotationCertificateFile,
  type CertificateRow,
} from '../../../../_shared/services/quotationCertificateService';
import {
  MARKED_FILTERS,
  VALIDITY,
  markedFilterOf,
  markedText,
} from '../../../../_shared/lib/quotationCertificateDisplay';
import { AddCertificateDialog } from './AddCertificateDialog';

const certificateHref = (projectId: string, documentId: string, certificateId: string) =>
  `/project-sales/${projectId}/quotation-documents/${documentId}/certification/${certificateId}`;

/** CERT-15: the other certificates that are the same file as this row. */
const alsoFiledAs = (row: CertificateRow) =>
  `Also filed as ${row.also_filed_as.map((o) => `${o.scheme} ${o.certificate_number}`).join(', ')}`;

/** CERT-TAB-UX: one line per row, so what used to be the second and third lines is the tooltip. */
const certificateTooltip = (row: CertificateRow) =>
  [row.certificate_number, row.title, row.also_filed_as.length > 0 ? alsoFiledAs(row) : null]
    .filter(Boolean)
    .join('\n');

/** CERT-16: a certificate whose code is not printed on its file is listed greyed. */
const isGrey = (row: CertificateRow) => row.verified === false;

const SOURCE_LABEL: Record<CertificateRow['source'], string> = { auto: 'Auto', manual: 'Added' };

const VALIDITY_FILTERS = (['valid', 'expiring', 'expired'] as const).map((value) => ({
  value,
  label: VALIDITY[value].label,
}));

const SOURCE_FILTERS = (['auto', 'manual'] as const).map((value) => ({
  value,
  label: SOURCE_LABEL[value],
}));

/** Ascending Rows marked puts the rows that need a person first, in the filter's order. */
const MARKED_RANK = (row: CertificateRow) => {
  const bucket = markedFilterOf(row.marked.state);
  const order = ['code_not_found', 'code_needed', 'no_text', 'no_file', 'edited', 'marked'];
  return bucket ? order.indexOf(bucket) : order.length;
};

type Filters = { scheme: string[]; validity: string[]; marked: string[]; source: string[] };
const NO_FILTERS: Filters = { scheme: [], validity: [], marked: [], source: [] };

function matches(row: CertificateRow, needle: string, f: Filters): boolean {
  if (f.scheme.length && !f.scheme.includes(row.scheme)) return false;
  if (f.validity.length && !f.validity.includes(row.validity_state)) return false;
  if (f.source.length && !f.source.includes(row.source)) return false;
  if (f.marked.length) {
    const bucket = markedFilterOf(row.marked.state);
    if (!bucket || !f.marked.includes(bucket)) return false;
  }
  if (!needle) return true;
  return [
    row.scheme,
    row.certificate_number,
    row.title,
    row.certifying_body,
    ...row.also_filed_as.map((o) => `${o.scheme} ${o.certificate_number}`),
    ...row.products.map((p) => p.product_code),
  ]
    .filter(Boolean)
    .join(' ')
    .toLowerCase()
    .includes(needle);
}

function labelsOf(values: string[], options: readonly { value: string; label: string }[]) {
  return values.map((v) => options.find((o) => o.value === v)?.label ?? v);
}

async function saveFile(projectId: string, documentId: string, row: CertificateRow) {
  try {
    const bytes = await fetchQuotationCertificateFile(projectId, documentId, row.certificate_id);
    const url = URL.createObjectURL(new Blob([bytes], { type: 'application/pdf' }));
    const link = document.createElement('a');
    link.href = url;
    link.download = `${row.scheme} ${row.certificate_number}.pdf`;
    link.click();
    URL.revokeObjectURL(url);
  } catch (error) {
    toast.error(error instanceof Error ? error.message : 'Could not download the file');
  }
}

function FilterField({
  id,
  title,
  value,
  onChange,
  options,
}: {
  id: string;
  title: string;
  value: string[];
  onChange: (next: string[]) => void;
  options: readonly { value: string; label: string }[];
}) {
  return (
    <div className="flex flex-col gap-1.5">
      <Label htmlFor={id}>{title}</Label>
      <SearchableMultiSelect
        id={id}
        value={value}
        onChange={onChange}
        options={options.map((o) => ({ value: o.value, label: o.label }))}
        placeholder={`${title}: any`}
        clearable
        renderTriggerLabel={(chosen) =>
          chosen.length ? (
            <span className="block truncate">
              {multiChipLabel(title, chosen.map((o) => o.label))}
            </span>
          ) : (
            <span className="text-muted-foreground">{title}: any</span>
          )
        }
      />
    </div>
  );
}

/**
 * The Certification tab: the distinct certificates of the quoted products, one line per row, with
 * the standard toolbar (search, filters, Columns) and client-side sorting on every column (a tab
 * holds one quote's rows, so nothing is paged on the server). The row opens the certificate at its
 * first box; Download certificates PDF is the toolbar's one export.
 */
export function QuotationCertificatesList({
  projectId,
  documentId,
}: {
  projectId: string;
  documentId: string;
}) {
  const router = useRouter();
  /** The row the right-click menu was opened on. */
  const [menuRow, setMenuRow] = React.useState<CertificateRow | null>(null);
  const list = useQuotationCertificates(projectId, documentId);
  const { exportPdf } = useQuotationCertificateMutations(projectId, documentId);
  const [adding, setAdding] = React.useState(false);
  const [search, setSearch] = React.useState('');
  const [filters, setFilters] = React.useState<Filters>(NO_FILTERS);
  const removal = useDeferredRowAction({
    actionKey: 'quotation_certificate.remove',
    entityType: 'quotation_certificate',
    verb: 'Removing',
    successMessage: 'Certificate removed',
    invalidateKeys: [quotationCertificatesKey(documentId)],
  });

  const all = React.useMemo(() => list.data?.items ?? [], [list.data]);
  const needle = search.trim().toLowerCase();
  const rows = React.useMemo(
    () => all.filter((row) => matches(row, needle, filters)),
    [all, needle, filters],
  );
  const canEdit = Boolean(list.data?.can_edit);
  const canAdd = Boolean(list.data?.can_add);
  const listed = React.useMemo(() => new Set(all.map((r) => r.certificate_id)), [all]);
  const schemeOptions = React.useMemo(
    () =>
      Array.from(new Set(all.map((r) => r.scheme).filter(Boolean)))
        .sort()
        .map((value) => ({ value, label: value })),
    [all],
  );
  const run = removal.run;
  const onRemove = React.useCallback(
    (row: CertificateRow) =>
      run({
        // One countdown per certificate, so two removes on a quote coexist.
        id: `${documentId}:${row.certificate_id}`,
        subject: `${row.scheme} ${row.certificate_number}`,
      }),
    [run, documentId],
  );

  const setFilter = (key: keyof Filters) => (next: string[]) =>
    setFilters((current) => ({ ...current, [key]: next }));
  const activeSummary = (
    [
      ['scheme', 'Scheme', schemeOptions],
      ['validity', 'Validity', VALIDITY_FILTERS],
      ['marked', 'Rows marked', MARKED_FILTERS],
      ['source', 'Source', SOURCE_FILTERS],
    ] as const
  )
    .filter(([key]) => filters[key].length > 0)
    .map(([key, title, options]) => ({
      label: multiChipLabel(title, labelsOf(filters[key], options)),
      onClear: () => setFilter(key)([]),
    }));
  const filtering = activeSummary.length > 0;

  const columns = React.useMemo<ColumnDef<CertificateRow>[]>(
    () => [
      {
        id: 'certificate',
        accessorFn: (row) => row.certificate_number,
        header: ({ column }) => <DataGridColumnHeader title="Certificate" column={column} />,
        cell: ({ row }) => (
          <span
            className={`block truncate font-medium ${isGrey(row.original) ? 'text-muted-foreground' : ''}`}
            title={certificateTooltip(row.original)}
          >
            {row.original.certificate_number}
          </span>
        ),
        size: 150,
        minSize: 110,
        meta: { headerTitle: 'Certificate' },
      },
      {
        id: 'scheme',
        accessorFn: (row) => row.scheme,
        header: ({ column }) => <DataGridColumnHeader title="Scheme" column={column} />,
        cell: ({ row }) => (
          <span
            className={`block truncate ${isGrey(row.original) ? 'text-muted-foreground' : ''}`}
            title={row.original.scheme}
          >
            {row.original.scheme}
          </span>
        ),
        size: 80,
        minSize: 64,
        meta: { headerTitle: 'Scheme' },
      },
      {
        id: 'valid_until',
        // Undated certificates sort after every dated one.
        accessorFn: (row) => row.valid_until ?? '9999-12-31',
        header: ({ column }) => <DataGridColumnHeader title="Valid until" column={column} />,
        cell: ({ row }) => {
          const validity = VALIDITY[row.original.validity_state];
          const date = row.original.valid_until ? formatDateInMalaysia(row.original.valid_until) : '';
          return (
            <span className="flex min-w-0 items-center gap-1.5 whitespace-nowrap">
              {date && (
                <span className="truncate" title={date}>
                  {date}
                </span>
              )}
              <Badge variant={validity.variant} appearance="light" size="sm" className="shrink-0">
                {validity.label}
              </Badge>
            </span>
          );
        },
        size: 170,
        minSize: 140,
        meta: { headerTitle: 'Valid until' },
      },
      {
        id: 'products',
        accessorFn: (row) => row.products.map((p) => p.product_code).join(', '),
        header: ({ column }) => <DataGridColumnHeader title="Quoted products" column={column} />,
        cell: ({ row }) => {
          const text = row.original.products.map((p) => p.product_code).join(', ');
          return (
            <span
              className={`block truncate ${isGrey(row.original) ? 'text-muted-foreground' : ''}`}
              title={text}
            >
              {text}
            </span>
          );
        },
        size: 200,
        minSize: 120,
        meta: { headerTitle: 'Quoted products' },
      },
      {
        id: 'marked',
        accessorFn: (row) => MARKED_RANK(row) * 1000 - row.marked.count,
        header: ({ column }) => <DataGridColumnHeader title="Rows marked" column={column} />,
        cell: ({ row }) => {
          const text = markedText(row.original.marked);
          if (isGrey(row.original)) {
            return (
              <Badge variant="secondary" appearance="light" size="sm" title={text}>
                {text}
              </Badge>
            );
          }
          return (
            <span className="block truncate" title={text}>
              {text}
            </span>
          );
        },
        size: 140,
        minSize: 110,
        meta: { headerTitle: 'Rows marked' },
      },
      {
        id: 'source',
        accessorFn: (row) => SOURCE_LABEL[row.source],
        header: ({ column }) => <DataGridColumnHeader title="Source" column={column} />,
        cell: ({ row }) => <span className="block truncate">{SOURCE_LABEL[row.original.source]}</span>,
        size: 80,
        minSize: 64,
        meta: { headerTitle: 'Source' },
      },
    ],
    [],
  );

  const open = (row: CertificateRow) =>
    router.push(certificateHref(projectId, documentId, row.certificate_id));

  return (
    <>
      {/* The row actions are its right-click menu (long-press on touch), as on the Purchase
          orders tab: no "..." button on the row (owner: right-click over icons). */}
      <ContextMenu modal={false}>
        <ContextMenuTrigger asChild>
          <div
            // Capture phase: a right-click outside a certificate row stops here, so the
            // browser's own menu shows instead of an empty one.
            onContextMenuCapture={(event) => {
              const rowEl = (event.target as Element).closest('[data-certificate-id]');
              const id = rowEl?.getAttribute('data-certificate-id');
              const hit = id ? all.find((r) => r.certificate_id === id) : undefined;
              if (!hit) {
                event.stopPropagation();
                return;
              }
              setMenuRow(hit);
            }}
          >
      <PanelDataGrid<CertificateRow>
        title="Certificates"
        listingKey="projects.projects.view::quotation-certificates"
        columns={columns}
        rows={rows}
        getRowId={(row) => row.certificate_id}
        isLoading={list.isLoading}
        error={list.error}
        onRetry={() => list.refetch()}
        sortable
        pageSize={50}
        pageResetKey={`${needle}|${JSON.stringify(filters)}`}
        emptyTitle={
          all.length > 0 && (needle || filtering) ? 'Nothing matches' : 'No certificates'
        }
        emptyBody={
          all.length > 0 && (needle || filtering)
            ? 'Try another search or clear a filter.'
            : 'None of the quoted products has a certificate on file.'
        }
        onRowClick={open}
        rowAttributes={(row) => ({ 'data-certificate-id': row.certificate_id })}
        toolbar={({ table }) => (
          <DataGridListToolbar
            table={table}
            exportConfig={false}
            searchSlot={
              <ListSearchInput
                type="search"
                inputClassName="[&::-webkit-search-cancel-button]:appearance-none"
                value={search}
                onChange={setSearch}
                placeholder="Search certificates"
                aria-label="Search certificates"
                className="w-full sm:w-64"
              />
            }
            filters={{
              kind: 'custom',
              modal: false,
              active: filtering,
              activeCount: activeSummary.length,
              activeSummary,
              content: (
                <div className="flex w-64 flex-col gap-3">
                  <FilterField
                    id="cert-filter-scheme"
                    title="Scheme"
                    value={filters.scheme}
                    onChange={setFilter('scheme')}
                    options={schemeOptions}
                  />
                  <FilterField
                    id="cert-filter-validity"
                    title="Validity"
                    value={filters.validity}
                    onChange={setFilter('validity')}
                    options={VALIDITY_FILTERS}
                  />
                  <FilterField
                    id="cert-filter-marked"
                    title="Rows marked"
                    value={filters.marked}
                    onChange={setFilter('marked')}
                    options={MARKED_FILTERS}
                  />
                  <FilterField
                    id="cert-filter-source"
                    title="Source"
                    value={filters.source}
                    onChange={setFilter('source')}
                    options={SOURCE_FILTERS}
                  />
                </div>
              ),
            }}
            // In the Actions menu, not a second text button: two text buttons beside the
            // search clipped Add certificate at 375px, and the owner asked for fewer buttons.
            secondaryActionsAsMenu
            secondaryActions={[
              {
                key: 'download-certificates-pdf',
                label: 'Download certificates PDF',
                icon: FileDown,
                disabled: exportPdf.isPending,
                onClick: () => exportPdf.mutate(null),
              },
            ]}
            primaryAction={
              canAdd ? (
                <Button size="sm" onClick={() => setAdding(true)}>
                  <Plus className="size-4" aria-hidden />
                  Add certificate
                </Button>
              ) : undefined
            }
          />
        )}
      />
          </div>
        </ContextMenuTrigger>
        <ContextMenuContent className="w-48">
          {menuRow && (
            <>
              <ContextMenuItem onSelect={() => open(menuRow)}>Open</ContextMenuItem>
              <ContextMenuItem
                disabled={!menuRow.has_file}
                onSelect={() => void saveFile(projectId, documentId, menuRow)}
              >
                Download
              </ContextMenuItem>
              {canEdit && (
                <ContextMenuItem variant="destructive" onSelect={() => onRemove(menuRow)}>
                  Remove
                </ContextMenuItem>
              )}
            </>
          )}
        </ContextMenuContent>
      </ContextMenu>
      {canAdd && (
        <AddCertificateDialog
          open={adding}
          onOpenChange={setAdding}
          projectId={projectId}
          documentId={documentId}
          listed={listed}
        />
      )}
    </>
  );
}
