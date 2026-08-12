'use client';

import * as React from 'react';
import { useRouter } from 'next/navigation';
import type { ColumnDef, Table } from '@tanstack/react-table';
import { AlertTriangle, Plus, TriangleAlert } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { DataGridColumnHeader } from '@/components/ui/data-grid-column-header';
import { PanelDataGrid } from '../../_shared/components/PanelDataGrid';
import { formatDateInMalaysia } from '@/lib/helpers';
import { quotationStanding } from '../../_shared/lib/quotationDecision';
import { useQuotations } from '../../_shared/hooks/useProjects';
import {
  useQuotationDocumentMutations,
  useQuotationDocuments,
} from '../../_shared/hooks/useQuotationDocuments';
import type { QuotationDocument } from '../../_shared/services/quotationDocumentService';
import type { Project } from '../../_shared/types/project.types';
import { formatMyrExact, sumMoney } from '../../_shared/lib/money';

/**
 * Every quotation DOCUMENT on this project: one row per letterhead the customer receives.
 *
 * The list used to hold one row per scope revision, which is the wrong grain now that a
 * document carries several scopes and is issued as a whole: a customer holds "SRT/Q/2026/0141
 * (R2)", not "House Units v2". So the row is the document, the scopes are a count, and the
 * revision history lives on the document's own page.
 *
 * The two alert badges stay in the toolbar. They are the guardrail management asked for, they
 * are counted across the project's scopes rather than per document, and a number is not a
 * second call to action competing with the button beside it.
 */
export function QuotationsPanel({ project }: { project: Project }) {
  const router = useRouter();
  const documents = useQuotationDocuments(project.id);
  const scopes = useQuotations(project.id);
  const { create } = useQuotationDocumentMutations(project.id);

  const rows = React.useMemo(() => documents.data ?? [], [documents.data]);

  const scopeRows = React.useMemo(() => scopes.data ?? [], [scopes.data]);
  const totalBelowFloor = scopeRows.reduce((sum, row) => sum + row.below_floor_count, 0);
  const totalNonStandard = scopeRows.reduce((sum, row) => sum + row.non_standard_count, 0);

  const columns = React.useMemo<ColumnDef<QuotationDocument>[]>(
    () => [
      {
        id: 'our_ref',
        accessorFn: (row) => row.our_ref ?? row.document_no,
        header: ({ column }) => <DataGridColumnHeader title="Reference" column={column} />,
        cell: ({ row }) => {
          const reference = row.original.our_ref ?? row.original.document_no;
          return (
            <span className="truncate text-sm font-medium" title={reference}>
              {reference}
            </span>
          );
        },
        size: 190,
        meta: { headerTitle: 'Reference' },
      },
      {
        id: 'subject_title',
        accessorFn: (row) => row.subject_title ?? '',
        header: ({ column }) => <DataGridColumnHeader title="Subject" column={column} />,
        cell: ({ row }) =>
          row.original.subject_title ? (
            <span className="truncate text-sm" title={row.original.subject_title}>
              {row.original.subject_title}
            </span>
          ) : (
            <span className="text-muted-foreground">-</span>
          ),
        size: 260,
        meta: { headerTitle: 'Subject' },
      },
      {
        id: 'recipient_name_snapshot',
        accessorFn: (row) => row.recipient_name_snapshot ?? '',
        header: ({ column }) => <DataGridColumnHeader title="Recipient" column={column} />,
        cell: ({ row }) =>
          row.original.recipient_name_snapshot ? (
            <span className="truncate text-sm" title={row.original.recipient_name_snapshot}>
              {row.original.recipient_name_snapshot}
            </span>
          ) : (
            <span className="text-muted-foreground">-</span>
          ),
        size: 200,
        meta: { headerTitle: 'Recipient' },
      },
      {
        id: 'scope_count',
        accessorFn: (row) => row.scopes.length,
        header: ({ column }) => <DataGridColumnHeader title="Scopes" column={column} />,
        cell: ({ row }) => <span className="text-sm">{row.original.scopes.length}</span>,
        size: 100,
        meta: { headerTitle: 'Scopes' },
      },
      {
        // Draft / Issued, and - once the customer has answered - what they answered.
        //
        // The client asked "when i request changes, how can i see it from the system?", and a
        // salesperson scanning this tab is the second place that question gets asked. It rides
        // this column rather than a new one because the customer's answer IS where the quotation
        // stands: a second, mostly-empty column would push the money off a 375px screen.
        id: 'status',
        accessorFn: (row) => quotationStanding(row).label,
        header: ({ column }) => <DataGridColumnHeader title="Status" column={column} />,
        cell: ({ row }) => {
          const standing = quotationStanding(row.original);
          return (
            <Badge variant={standing.variant} appearance="light" className="text-[11px]">
              {standing.label}
            </Badge>
          );
        },
        size: 150,
        meta: { headerTitle: 'Status' },
      },
      {
        id: 'grand_total',
        accessorFn: (row) => row.grand_total,
        header: ({ column }) => <DataGridColumnHeader title="Value" column={column} />,
        cell: ({ row }) => (
          <span className="block truncate text-end text-sm font-medium tabular-nums">
            {formatMyrExact(row.original.grand_total)}
          </span>
        ),
        // Summed off the STRINGS, to the cent: a float sum of a page of quotations drifts, and
        // a footer that disagrees with the documents above it by a cent is worse than no footer.
        footer: ({ table }: { table: Table<QuotationDocument> }) => {
          const total = sumMoney(
            table.getCoreRowModel().rows.map((row) => row.original.grand_total),
          );
          return (
            <span className="block text-end tabular-nums">
              {total === null ? '-' : formatMyrExact(total)}
            </span>
          );
        },
        size: 160,
        meta: { headerTitle: 'Value' },
      },
      {
        id: 'doc_date',
        accessorFn: (row) => row.doc_date ?? '',
        header: ({ column }) => <DataGridColumnHeader title="Dated" column={column} />,
        cell: ({ row }) => {
          const dated = row.original.doc_date
            ? formatDateInMalaysia(row.original.doc_date)
            : '';
          return dated ? (
            <span className="truncate text-sm">{dated}</span>
          ) : (
            <span className="text-muted-foreground">-</span>
          );
        },
        size: 130,
        meta: { headerTitle: 'Dated' },
      },
    ],
    [],
  );

  return (
    <PanelDataGrid
      title="Quotations"
      toolbar={
        <>
          {totalBelowFloor > 0 && (
            <Badge variant="destructive" appearance="light" className="gap-1">
              <AlertTriangle className="size-3" aria-hidden />
              {`${totalBelowFloor} below the price floor`}
            </Badge>
          )}
          {totalNonStandard > 0 && (
            <Badge variant="warning" appearance="light" className="gap-1">
              <TriangleAlert className="size-3" aria-hidden />
              {`${totalNonStandard} non-standard`}
            </Badge>
          )}
          {project.can_edit && (
            <Button
              type="button"
              size="sm"
              disabled={create.isPending}
              // Nothing is asked for: the reference, the recipient and the subject are all
              // derived from the project, so creating one is a single press and the salesperson
              // lands on it to price it.
              onClick={async () => {
                try {
                  const created = await create.mutateAsync({});
                  router.push(
                    `/project-sales/${project.id}/quotation-documents/${created.id}`,
                  );
                } catch {
                  // The mutation already toasted the reason; the list stays as it was.
                }
              }}
            >
              <Plus className="size-4" aria-hidden />
              Add a quotation
            </Button>
          )}
        </>
      }
      columns={columns}
      rows={rows}
      getRowId={(row) => row.id}
      // Suffixed on purpose: the column SET changed when the list went from one row per scope
      // revision to one row per document, and a saved per-user order for the old set appends
      // the new columns to the end, which reads as scrambled.
      listingKey="projects.projects.view::project-quotation-documents"
      isLoading={documents.isLoading}
      error={documents.isError ? documents.error : undefined}
      emptyTitle="Nothing quoted yet"
      searchPlaceholder="Search quotations"
      searchOf={(row) =>
        [row.our_ref, row.document_no, row.subject_title, row.recipient_name_snapshot]
          .filter(Boolean)
          .join(' ')
      }
      pageSize={15}
      // The row is the way in, and it goes to the document's own page: a list answers "what do
      // we have", a document answers "what is in this one", and stacking them cramps both.
      onRowClick={(row) =>
        router.push(`/project-sales/${project.id}/quotation-documents/${row.id}`)
      }
    />
  );
}

export function formatMyr(value: string): string {
  // Delegates to the ONE money renderer. This used to be its own `Number()` +
  // `toLocaleString` implementation - the float path every module docstring in
  // `_shared/lib/money` exists to forbid - and the third spelling of "RM x,xxx.xx"
  // in one directory. The name survives because six screens import it.
  return formatMyrExact(value);
}
