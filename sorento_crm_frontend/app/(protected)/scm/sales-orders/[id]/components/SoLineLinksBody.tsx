'use client';

import { useMemo } from 'react';
import { type ColumnDef } from '@tanstack/react-table';

import { DrillTable, RIGHT } from '../../../components/PlanRowDialog';
import { EM_DASH, fmtDate } from '../../../lib/format';
import { lateDaysOf } from '../../../../project-sales/_shared/lib/orderInquiryWorklist';
import type { SalesOrderLineLink } from '../../../types/scm.types';

/**
 * What one sales-order line is linked to - the lightbox the "Linked" column opens (R5,
 * AC-L4), replacing the inline multi-link text the "Linked to" cell used to render.
 *
 * NOTE (measured, R5): `SalesOrderLineLink` carries no purchase-order/SPO id, only the
 * document NUMBER, so the Document cell is text here, not a link. Linking it needs a
 * backend field and is out of scope for this frontend-only slice.
 */

function textCell(value: string | null | undefined) {
  return value ? value : <span className="text-muted-foreground">{EM_DASH}</span>;
}

export function SoLineLinksBody({ links }: { links: SalesOrderLineLink[] }) {
  const columns = useMemo<ColumnDef<SalesOrderLineLink>[]>(
    () => [
      {
        id: 'kind',
        header: 'Kind',
        cell: ({ row }) => (
          <span className="rounded-sm bg-muted px-1 py-0.5 text-2xs font-medium uppercase text-muted-foreground">
            {row.original.kind}
          </span>
        ),
        size: 80,
      },
      {
        id: 'document',
        header: 'Document',
        cell: ({ row }) => {
          const link = row.original;
          const withLabel = link.line_label ? `${link.document} ${link.line_label}` : link.document;
          return textCell(withLabel);
        },
        size: 170,
      },
      {
        id: 'qty',
        header: 'Qty',
        cell: ({ row }) => row.original.qty,
        size: 90,
        meta: RIGHT,
      },
      {
        id: 'lands_at',
        header: 'Lands at',
        cell: ({ row }) => textCell(row.original.location),
        size: 150,
      },
      {
        id: 'eta',
        header: 'ETA',
        cell: ({ row }) => textCell(row.original.expected_date ? fmtDate(row.original.expected_date) : null),
        size: 110,
        meta: RIGHT,
      },
      {
        id: 'late',
        header: 'Late',
        cell: ({ row }) => {
          const link = row.original;
          if (!link.late) return <span className="text-muted-foreground">{EM_DASH}</span>;
          const days = lateDaysOf(link);
          return (
            <span className="rounded-sm bg-amber-100 px-1 py-0.5 text-2xs font-medium text-amber-800">
              {days !== null ? `late ${days} d` : 'late'}
            </span>
          );
        },
        size: 110,
      },
    ],
    [],
  );

  return (
    <DrillTable
      columns={columns}
      rows={links}
      getRowId={(link, index) => `${link.kind}-${link.document}-${index}`}
      emptyMessage="Not linked."
    />
  );
}

export default SoLineLinksBody;
