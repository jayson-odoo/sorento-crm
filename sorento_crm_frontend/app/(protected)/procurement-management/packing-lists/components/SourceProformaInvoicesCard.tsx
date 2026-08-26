'use client';

import Link from 'next/link';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { formatDate } from '@/lib/helpers';
import { usePackingListSourceInvoices } from '../hooks/usePackingLists';

/**
 * Which proforma invoices this container was drafted from, and how much of each came here
 * (AC-F9).
 *
 * Always rendered with its own empty state, per the CRUD standard: a container loaded from
 * a real packing-list upload has no proforma invoice behind it, and "none" is the honest
 * answer rather than a section that quietly disappears.
 *
 * "qty from this PI of its total" is the load-bearing figure: one invoice may be split
 * across two containers (Q9), so 200 of 500 here means 300 is somewhere else, and a card
 * showing only 200 would read as the whole invoice.
 */
export function SourceProformaInvoicesCard({ packingListId }: { packingListId: string }) {
  const { data, isLoading } = usePackingListSourceInvoices(packingListId);
  const invoices = data?.invoices ?? [];

  return (
    <Card className="mt-6">
      <CardHeader>
        <CardTitle>Source proforma invoices</CardTitle>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <Skeleton className="h-20 w-full rounded-lg" />
        ) : invoices.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            This container was not drafted from a proforma invoice. Its lines came from the
            packing list itself.
          </p>
        ) : (
          <div className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Proforma invoice</TableHead>
                  <TableHead>Supplier</TableHead>
                  <TableHead>Invoice date</TableHead>
                  {/* WHICH version the container was loaded from (AC-F9). "PI-x" alone does
                      not say whether its goods were priced on the one still in force. */}
                  <TableHead>Revision</TableHead>
                  <TableHead className="text-end">Lines</TableHead>
                  <TableHead className="text-end">Quantity here</TableHead>
                  <TableHead className="text-end">Amount</TableHead>
                  <TableHead />
                </TableRow>
              </TableHeader>
              <TableBody>
                {invoices.map((pi) => (
                  <TableRow key={pi.id}>
                    <TableCell>
                      <span className="font-medium">{pi.pi_number}</span>
                    </TableCell>
                    <TableCell>
                      <span className="block max-w-[200px] truncate" title={pi.supplier_name ?? undefined}>
                        {pi.supplier_name ?? '-'}
                      </span>
                    </TableCell>
                    <TableCell>
                      {pi.invoice_date ? formatDate(new Date(pi.invoice_date)) : '-'}
                    </TableCell>
                    <TableCell>
                      {(pi.revision_count ?? 1) > 1 ? (
                        <span className="flex flex-wrap items-center gap-1.5">
                          Revision {pi.revision_no} of {pi.revision_count}
                          {pi.status === 'superseded' ? (
                            <Badge variant="secondary" appearance="light">
                              Superseded
                            </Badge>
                          ) : null}
                        </span>
                      ) : (
                        <span className="text-muted-foreground">-</span>
                      )}
                    </TableCell>
                    <TableCell className="text-end tabular-nums">
                      {pi.lines} of {pi.total_lines}
                    </TableCell>
                    <TableCell className="text-end tabular-nums">
                      {pi.qty} of {pi.total_qty}
                    </TableCell>
                    <TableCell className="text-end tabular-nums">
                      {pi.amount == null
                        ? '-'
                        : `${pi.currency ?? ''} ${pi.amount.toLocaleString('en-GB', {
                            minimumFractionDigits: 2,
                            maximumFractionDigits: 2,
                          })}`.trim()}
                    </TableCell>
                    <TableCell className="text-end">
                      <Link
                        href={`/scm/proforma-invoices/${pi.id}`}
                        className="text-primary hover:underline"
                      >
                        Open
                      </Link>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

export default SourceProformaInvoicesCard;
