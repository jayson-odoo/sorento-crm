'use client';

import * as React from 'react';
import { useRouter } from 'next/navigation';
import type { ColumnDef } from '@tanstack/react-table';
import { Eye, FileDown, Plus, Trash2 } from 'lucide-react';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { DataGridColumnHeader } from '@/components/ui/data-grid-column-header';
import { PanelDataGrid } from '@/components/common/PanelDataGrid';
import { RowActionsMenu } from '@/components/common/RowActionsMenu';
import type { RecordAction } from '@/components/common/recordActions';
import { useDeferredAction } from '@/hooks/useDeferredAction';
import { formatDateTimeInMalaysia } from '@/lib/helpers';

import {
  specSheetListKey,
  useSpecSheetMutations,
  useSpecSheets,
} from '../../../../_shared/hooks/useSpecSheet';
import type { SpecSheetListRow } from '../../../../_shared/services/specSheetService';
import { CreateSpecSheetDialog } from './CreateSpecSheetDialog';
import { useQuotationDocumentScreen } from './QuotationDocumentContext';

const sheetHref = (projectId: string, documentId: string, sheetId: string) =>
  `/project-sales/${projectId}/quotation-documents/${documentId}/spec-sheet/${sheetId}`;

/** The row's "..." menu: View, Export PDF, and (with the edit right) Delete as a countdown. */
function SpecSheetRowMenu({
  row,
  projectId,
  documentId,
  canEdit,
  onExport,
}: {
  row: SpecSheetListRow;
  projectId: string;
  documentId: string;
  canEdit: boolean;
  onExport: (sheetId: string) => void;
}) {
  const router = useRouter();
  const deletion = useDeferredAction({
    actionKey: 'quotation_spec_sheet.delete',
    entityType: 'quotation_spec_sheet',
    entityId: row.id,
    verb: 'Deleting',
    subject: row.label,
    surface: 'toast',
    successMessage: 'Spec sheet deleted',
    invalidateKeys: [specSheetListKey(documentId)],
  });
  const actions: RecordAction[] = [
    {
      key: 'quotation_spec_sheet.view',
      label: 'View',
      icon: Eye,
      run: () => router.push(sheetHref(projectId, documentId, row.id)),
    },
    {
      key: 'quotation_spec_sheet.export',
      label: 'Export PDF',
      icon: FileDown,
      run: () => onExport(row.id),
    },
  ];
  if (canEdit) {
    actions.push({
      key: 'quotation_spec_sheet.delete',
      label: 'Delete',
      icon: Trash2,
      kind: 'destructive',
      disabled: deletion.isPending,
      run: () => deletion.start(),
    });
  }
  return <RowActionsMenu actions={actions} ariaLabel={row.label} />;
}

/**
 * The Spec sheet tab: the saved spec sheets of this quotation, newest first. The row opens the
 * sheet; the one CTA is Create spec sheet in the header.
 */
export function QuotationSpecSheetsList() {
  const { projectId, documentId, canEdit } = useQuotationDocumentScreen();
  const router = useRouter();
  const list = useSpecSheets(projectId, documentId);
  const { exportPdf } = useSpecSheetMutations(projectId, documentId);
  const [creating, setCreating] = React.useState(false);

  const rows = React.useMemo(() => list.data?.items ?? [], [list.data]);
  const reason = list.data?.create_disabled_reason ?? null;
  const onExport = exportPdf.mutate;

  const columns = React.useMemo<ColumnDef<SpecSheetListRow>[]>(
    () => [
      {
        accessorKey: 'label',
        header: ({ column }) => (
          <DataGridColumnHeader title="No." column={column} />
        ),
        cell: ({ row }) => (
          <span
            className="block truncate font-medium"
            title={row.original.label}
          >
            {row.original.label}
          </span>
        ),
        size: 80,
        minSize: 60,
        enableSorting: false,
        meta: { headerTitle: 'No.' },
      },
      {
        id: 'revision',
        header: ({ column }) => (
          <DataGridColumnHeader title="Revision" column={column} />
        ),
        cell: ({ row }) => (
          <span className="block truncate" title={row.original.source_label}>
            {row.original.source_label}
          </span>
        ),
        size: 200,
        minSize: 130,
        enableSorting: false,
        meta: { headerTitle: 'Revision' },
      },
      {
        id: 'templates',
        header: ({ column }) => (
          <DataGridColumnHeader title="Templates" column={column} />
        ),
        cell: ({ row }) => {
          const { cover_name, page_name, single_name } = row.original;
          return (
            <span
              className="block truncate"
              title={[cover_name, page_name, single_name]
                .filter(Boolean)
                .join(' / ')}
            >
              {cover_name}
            </span>
          );
        },
        size: 200,
        minSize: 130,
        enableSorting: false,
        meta: { headerTitle: 'Templates' },
      },
      {
        id: 'pages',
        header: ({ column }) => (
          <DataGridColumnHeader title="Pages" column={column} />
        ),
        cell: ({ row }) => (
          <span className="flex items-center gap-1 whitespace-nowrap">
            {row.original.page_count}
            {row.original.edited_count > 0 && (
              <Badge
                variant="warning"
                appearance="light"
                size="sm"
                className="shrink-0"
              >
                {row.original.edited_count} edited
              </Badge>
            )}
          </span>
        ),
        size: 130,
        minSize: 90,
        enableSorting: false,
        meta: { headerTitle: 'Pages' },
      },
      {
        id: 'created_by',
        header: ({ column }) => (
          <DataGridColumnHeader title="Created by" column={column} />
        ),
        cell: ({ row }) => (
          <span className="block truncate" title={row.original.created_by_name}>
            {row.original.created_by_name}
          </span>
        ),
        size: 150,
        minSize: 100,
        enableSorting: false,
        meta: { headerTitle: 'Created by' },
      },
      {
        id: 'created',
        header: ({ column }) => (
          <DataGridColumnHeader title="Created" column={column} />
        ),
        cell: ({ row }) => {
          const text = row.original.created_at
            ? formatDateTimeInMalaysia(row.original.created_at)
            : '';
          return (
            <span className="block truncate" title={text}>
              {text}
            </span>
          );
        },
        size: 160,
        minSize: 120,
        enableSorting: false,
        meta: { headerTitle: 'Created' },
      },
      {
        id: 'updated',
        header: ({ column }) => (
          <DataGridColumnHeader title="Last edited" column={column} />
        ),
        cell: ({ row }) => {
          const text = row.original.updated_at
            ? formatDateTimeInMalaysia(row.original.updated_at)
            : '';
          return (
            <span className="block truncate" title={text}>
              {text}
            </span>
          );
        },
        size: 160,
        minSize: 120,
        enableSorting: false,
        meta: { headerTitle: 'Last edited' },
      },
      {
        id: 'actions',
        header: () => <span className="sr-only">Actions</span>,
        cell: ({ row }) => (
          <SpecSheetRowMenu
            row={row.original}
            projectId={projectId}
            documentId={documentId}
            canEdit={canEdit}
            onExport={onExport}
          />
        ),
        size: 56,
        minSize: 56,
        enableSorting: false,
        enableResizing: false,
        meta: { headerTitle: 'Actions' },
      },
    ],
    [projectId, documentId, canEdit, onExport],
  );

  return (
    <>
      <PanelDataGrid<SpecSheetListRow>
        title="Spec sheets"
        listingKey="projects.projects.view::quotation-spec-sheets"
        columns={columns}
        rows={rows}
        getRowId={(row) => row.id}
        isLoading={list.isLoading}
        error={list.error}
        onRetry={() => list.refetch()}
        emptyTitle={reason ? 'No lines yet' : 'No spec sheets yet'}
        emptyBody={
          reason
            ? 'Add products on the Lines tab.'
            : 'A spec sheet prints a cover and one page per item of the quotation.'
        }
        onRowClick={(row) =>
          router.push(sheetHref(projectId, documentId, row.id))
        }
        toolbar={
          canEdit ? (
            // The reason sits on the button itself: the test and the hover both read it there.
            <Button
              size="sm"
              disabled={
                Boolean(reason) || list.isLoading || Boolean(list.error)
              }
              title={reason ?? undefined}
              onClick={() => setCreating(true)}
            >
              <Plus className="size-4" aria-hidden />
              Create spec sheet
            </Button>
          ) : null
        }
      />
      {canEdit && (
        <CreateSpecSheetDialog
          open={creating}
          onOpenChange={setCreating}
          projectId={projectId}
          documentId={documentId}
        />
      )}
    </>
  );
}
