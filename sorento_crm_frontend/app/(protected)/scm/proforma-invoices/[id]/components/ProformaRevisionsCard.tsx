'use client';

import Link from 'next/link';
import { Badge } from '@/components/ui/badge';
import { Card, CardHeader, CardHeading, CardTitle } from '@/components/ui/card';
import { EM_DASH, fmtDate, fmtQty, fmtSupplierCost } from '../../../lib/format';
import type { ProformaInvoiceDetail } from '../../../services/proformaInvoiceService';

/**
 * The revision chain, and what the supplier changed in it (AC-E7, AC-E8, AC-E11).
 *
 * Always rendered, with an explicit empty state, per the CRUD standard: "this is the only
 * version they have sent" is a fact worth reading, and a section that appears only sometimes
 * is a section nobody learns where to find.
 *
 * The diff compares the two documents AS THE SUPPLIER SENT THEM - their frozen quantity and
 * price on both sides - so a line Sorento trimmed to fit the container is not reported as
 * something the supplier changed.
 *
 * READ-ONLY. "Mark as revision of" acts on the whole record, so it lives in the page
 * header's actions menu (`MarkAsRevisionDialog`) rather than inside this tab: a control that
 * only exists once you have found the right tab is a control nobody finds.
 */
export function ProformaRevisionsCard({ invoice }: { invoice: ProformaInvoiceDetail }) {
  const diff = invoice.diff;
  const chain = invoice.revisions ?? [];

  return (
    <Card>
      <CardHeader>
        <CardHeading>
          <CardTitle>Revisions</CardTitle>
        </CardHeading>
      </CardHeader>

      <div className="space-y-3 p-4 pt-0">
        {chain.length < 2 ? (
          <p className="text-sm text-muted-foreground">
            This is the only version the supplier has sent.
          </p>
        ) : (
          <>
            <p className="text-sm font-medium">
              Revision {invoice.revision_no} of {invoice.revision_count}
            </p>
            <ul className="divide-y divide-border rounded-lg border">
              {chain.map((rev) => (
                <li
                  key={rev.id}
                  className="flex flex-col gap-1 p-2.5 sm:flex-row sm:items-center sm:justify-between"
                >
                  <span className="flex min-w-0 flex-wrap items-center gap-2">
                    {rev.id === invoice.id ? (
                      <span className="truncate text-sm font-medium">{rev.pi_number}</span>
                    ) : (
                      <Link
                        href={`/scm/proforma-invoices/${rev.id}`}
                        className="truncate text-sm font-medium text-primary hover:underline"
                      >
                        {rev.pi_number}
                      </Link>
                    )}
                    <Badge
                      variant={rev.status === 'superseded' ? 'secondary' : 'success'}
                      appearance="light"
                    >
                      Revision {rev.revision_no}
                      {rev.status === 'superseded' ? ' - superseded' : ''}
                    </Badge>
                  </span>
                  <span className="shrink-0 text-xs text-muted-foreground">
                    {fmtDate(rev.invoice_date)} - {rev.line_count} lines -{' '}
                    {fmtSupplierCost(rev.total_amount, invoice.currency)}
                  </span>
                </li>
              ))}
            </ul>
          </>
        )}

        {diff ? (
          <div className="space-y-2">
            <p className="text-sm font-medium">
              {diff.price_changed_lines > 0
                ? `Price changed on ${diff.price_changed_lines} ${diff.price_changed_lines === 1 ? 'line' : 'lines'}`
                : 'No price changed'}
              <span className="ms-1 font-normal text-muted-foreground">
                against {diff.compared_to_pi_number}
                {diff.qty_changed_lines > 0
                  ? `, quantity on ${diff.qty_changed_lines}`
                  : ''}
                {diff.added_lines > 0 ? `, ${diff.added_lines} added` : ''}
                {diff.removed_lines > 0 ? `, ${diff.removed_lines} removed` : ''}
              </span>
            </p>
            {diff.changes.length === 0 ? (
              <p className="text-sm text-muted-foreground">
                The supplier sent the same figures again.
              </p>
            ) : (
              <ul className="divide-y divide-border rounded-lg border text-xs">
                {diff.changes.map((change) => (
                  <li
                    key={`${change.item_code}-${change.occurrence}-${change.status}`}
                    className="flex flex-col gap-1 p-2.5 sm:flex-row sm:items-center sm:justify-between"
                  >
                    <span className="flex min-w-0 items-center gap-2">
                      <span className="truncate font-medium" title={change.item_code}>
                        {change.item_code}
                      </span>
                      {change.status !== 'changed' ? (
                        <Badge variant="secondary" appearance="light">
                          {change.status === 'added' ? 'Added' : 'Removed'}
                        </Badge>
                      ) : null}
                    </span>
                    <span className="flex shrink-0 flex-wrap gap-3 tabular-nums">
                      {change.unit_price_changed ? (
                        <span>
                          Price{' '}
                          <span className="text-muted-foreground line-through">
                            {change.unit_price_was == null
                              ? EM_DASH
                              : fmtSupplierCost(change.unit_price_was, invoice.currency)}
                          </span>{' '}
                          <span className="font-medium">
                            {change.unit_price_now == null
                              ? EM_DASH
                              : fmtSupplierCost(change.unit_price_now, invoice.currency)}
                          </span>
                        </span>
                      ) : null}
                      {change.qty_changed ? (
                        <span>
                          Qty{' '}
                          <span className="text-muted-foreground line-through">
                            {change.qty_was == null ? EM_DASH : fmtQty(change.qty_was)}
                          </span>{' '}
                          <span className="font-medium">
                            {change.qty_now == null ? EM_DASH : fmtQty(change.qty_now)}
                          </span>
                        </span>
                      ) : null}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </div>
        ) : null}
      </div>
    </Card>
  );
}

export default ProformaRevisionsCard;
