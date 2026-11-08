'use client';

import * as React from 'react';
import { useRouter } from 'next/navigation';
import type { ColumnDef } from '@tanstack/react-table';
import { Download, Eye, FileDown, Plus, Trash2 } from 'lucide-react';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { DataGridColumnHeader } from '@/components/ui/data-grid-column-header';
import { PanelDataGrid } from '@/components/common/PanelDataGrid';
import { RowActionsMenu } from '@/components/common/RowActionsMenu';
import type { RecordAction } from '@/components/common/recordActions';
import { useDeferredRowAction } from '@/hooks/useDeferredRowAction';
import { formatDateInMalaysia } from '@/lib/helpers';
import { toast } from '@/lib/toast';

import {
  quotationCertificatesKey,
  useQuotationCertificateMutations,
  useQuotationCertificates,
} from '../../../../_shared/hooks/useQuotationCertificates';
import {
  fetchQuotationCertificateFile,
  type CertificateRow,
  type CertificateValidity,
  type MarkedState,
} from '../../../../_shared/services/quotationCertificateService';
import { AddCertificateDialog } from './AddCertificateDialog';

const certificateHref = (projectId: string, documentId: string, certificateId: string) =>
  `/project-sales/${projectId}/quotation-documents/${documentId}/certification/${certificateId}`;

const VALIDITY: Record<CertificateValidity, { label: string; variant: 'success' | 'warning' | 'destructive' | 'secondary' }> = {
  valid: { label: 'Valid', variant: 'success' },
  expiring: { label: 'Expiring', variant: 'warning' },
  expired: { label: 'Expired', variant: 'destructive' },
  unknown: { label: 'Unknown', variant: 'secondary' },
};

const MARKED_WORDS: Record<MarkedState, string> = {
  found: 'found',
  suggested: 'suggested, check',
  edited: 'edited',
  none: 'no quoted product',
  no_text: 'no text, draw the box',
  not_found: 'not found',
  no_file: 'no file',
  code_needed: 'code needed',
  not_on_certificate: 'not found on certificate',
};

function markedText(marked: CertificateRow['marked']): string {
  if (marked.state === 'none' || marked.state === 'no_file' || marked.state === 'no_text') {
    return MARKED_WORDS[marked.state];
  }
  const rows = `${marked.count} ${marked.count === 1 ? 'row' : 'rows'}`;
  return `${rows}, ${MARKED_WORDS[marked.state]}`;
}

/** CERT-16: a certificate whose code is not printed on its file is listed greyed. */
const isGrey = (row: CertificateRow) => row.verified === false;

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

/** The row's "..." menu: Open, Download and (with the edit right) Remove as a countdown. */
function CertificateRowMenu({
  row,
  projectId,
  documentId,
  canEdit,
  onRemove,
}: {
  row: CertificateRow;
  projectId: string;
  documentId: string;
  canEdit: boolean;
  onRemove: (row: CertificateRow) => void;
}) {
  const router = useRouter();
  const actions: RecordAction[] = [
    {
      key: 'quotation_certificate.open',
      label: 'Open',
      icon: Eye,
      run: () => router.push(certificateHref(projectId, documentId, row.certificate_id)),
    },
    {
      key: 'quotation_certificate.download',
      label: 'Download',
      icon: Download,
      disabled: !row.has_file,
      run: () => void saveFile(projectId, documentId, row),
    },
  ];
  if (canEdit) {
    actions.push({
      key: 'quotation_certificate.remove',
      label: 'Remove',
      icon: Trash2,
      kind: 'destructive',
      run: () => onRemove(row),
    });
  }
  return <RowActionsMenu actions={actions} ariaLabel={`${row.scheme} ${row.certificate_number}`} />;
}

/**
 * The Certification tab: the distinct certificates of the quoted products. The row opens the
 * certificate page; Download certificates PDF is the toolbar's one export.
 */
export function QuotationCertificatesList({
  projectId,
  documentId,
}: {
  projectId: string;
  documentId: string;
}) {
  const router = useRouter();
  const list = useQuotationCertificates(projectId, documentId);
  const { exportPdf } = useQuotationCertificateMutations(projectId, documentId);
  const [adding, setAdding] = React.useState(false);
  const removal = useDeferredRowAction({
    actionKey: 'quotation_certificate.remove',
    entityType: 'quotation_certificate',
    verb: 'Removing',
    successMessage: 'Certificate removed',
    invalidateKeys: [quotationCertificatesKey(documentId)],
  });

  const rows = React.useMemo(() => list.data?.items ?? [], [list.data]);
  const canEdit = Boolean(list.data?.can_edit);
  const listed = React.useMemo(() => new Set(rows.map((r) => r.certificate_id)), [rows]);
  const run = removal.run;
  const onRemove = React.useCallback(
    (row: CertificateRow) =>
      run({
        id: documentId,
        subject: `${row.scheme} ${row.certificate_number}`,
        payload: { certificate_id: row.certificate_id },
      }),
    [run, documentId],
  );

  const columns = React.useMemo<ColumnDef<CertificateRow>[]>(
    () => [
      {
        id: 'certificate',
        header: ({ column }) => <DataGridColumnHeader title="Certificate" column={column} />,
        cell: ({ row }) => (
          <div className={isGrey(row.original) ? 'text-muted-foreground' : undefined}>
            <span className="block truncate font-medium" title={row.original.certificate_number}>
              {row.original.certificate_number}
            </span>
            {row.original.title && (
              <span className="block truncate text-xs text-muted-foreground" title={row.original.title}>
                {row.original.title}
              </span>
            )}
          </div>
        ),
        size: 220,
        minSize: 160,
        enableSorting: false,
        meta: { headerTitle: 'Certificate' },
      },
      {
        id: 'scheme',
        header: ({ column }) => <DataGridColumnHeader title="Scheme" column={column} />,
        cell: ({ row }) => (
          <span
            className={`block truncate ${isGrey(row.original) ? 'text-muted-foreground' : ''}`}
            title={row.original.scheme}
          >
            {row.original.scheme}
          </span>
        ),
        size: 90,
        minSize: 70,
        enableSorting: false,
        meta: { headerTitle: 'Scheme' },
      },
      {
        id: 'valid_until',
        header: ({ column }) => <DataGridColumnHeader title="Valid until" column={column} />,
        cell: ({ row }) => {
          const validity = VALIDITY[row.original.validity_state];
          const date = row.original.valid_until ? formatDateInMalaysia(row.original.valid_until) : '';
          return (
            <span className="flex items-center gap-1.5 whitespace-nowrap">
              {date && <span title={date}>{date}</span>}
              <Badge variant={validity.variant} appearance="light" size="sm" className="shrink-0">
                {validity.label}
              </Badge>
            </span>
          );
        },
        size: 190,
        minSize: 150,
        enableSorting: false,
        meta: { headerTitle: 'Valid until' },
      },
      {
        id: 'products',
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
        size: 240,
        minSize: 140,
        enableSorting: false,
        meta: { headerTitle: 'Quoted products' },
      },
      {
        id: 'marked',
        header: ({ column }) => <DataGridColumnHeader title="Rows marked" column={column} />,
        cell: ({ row }) => {
          const { marked } = row.original;
          if (isGrey(row.original)) {
            return (
              <Badge variant="secondary" appearance="light" size="sm">
                Not found on certificate
              </Badge>
            );
          }
          const text = markedText(marked);
          return (
            <span className="flex items-center gap-1.5">
              <span className="block truncate" title={text}>
                {text}
              </span>
              {marked.state === 'suggested' && (
                <Badge variant="warning" appearance="light" size="sm" className="shrink-0">
                  Suggested, check
                </Badge>
              )}
            </span>
          );
        },
        size: 230,
        minSize: 150,
        enableSorting: false,
        meta: { headerTitle: 'Rows marked' },
      },
      {
        id: 'source',
        header: ({ column }) => <DataGridColumnHeader title="Source" column={column} />,
        cell: ({ row }) => (
          <span className="block truncate">{row.original.source === 'manual' ? 'Added' : 'Auto'}</span>
        ),
        size: 90,
        minSize: 70,
        enableSorting: false,
        meta: { headerTitle: 'Source' },
      },
      {
        id: 'actions',
        header: () => <span className="sr-only">Actions</span>,
        cell: ({ row }) => (
          <CertificateRowMenu
            row={row.original}
            projectId={projectId}
            documentId={documentId}
            canEdit={canEdit}
            onRemove={onRemove}
          />
        ),
        size: 60,
        minSize: 56,
        enableSorting: false,
        enableResizing: false,
        meta: { headerTitle: 'Actions' },
      },
    ],
    [projectId, documentId, canEdit, onRemove],
  );

  return (
    <>
      <PanelDataGrid<CertificateRow>
        title="Certificates"
        listingKey="projects.projects.view::quotation-certificates"
        columns={columns}
        rows={rows}
        getRowId={(row) => row.certificate_id}
        isLoading={list.isLoading}
        error={list.error}
        onRetry={() => list.refetch()}
        emptyTitle="No certificates"
        emptyBody="None of the quoted products has a certificate on file."
        onRowClick={(row) => router.push(certificateHref(projectId, documentId, row.certificate_id))}
        toolbar={
          <div className="flex flex-wrap items-center gap-2">
            <Button
              size="sm"
              variant="outline"
              disabled={exportPdf.isPending}
              onClick={() => exportPdf.mutate(null)}
            >
              <FileDown className="size-4" aria-hidden />
              Download certificates PDF
            </Button>
            {canEdit && (
              <Button size="sm" onClick={() => setAdding(true)}>
                <Plus className="size-4" aria-hidden />
                Add certificate
              </Button>
            )}
          </div>
        }
      />
      {canEdit && (
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
