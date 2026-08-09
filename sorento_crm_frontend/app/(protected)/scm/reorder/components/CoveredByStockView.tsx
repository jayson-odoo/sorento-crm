'use client';

import { Card, CardHeader } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { Badge } from '@/components/ui/badge';
import { fmtInt, fmtMoney } from '../../lib/format';
import type { ReorderRecommendation } from '../types/reorder.types';

/**
 * Demand the location's own stock already covers.
 *
 * The engine used to write nothing for these, which meant it had quietly decided "use
 * stock" on the planner's behalf. CS has already filtered what needs buying against what
 * the branch holds, so a line reaching the plan is a real requirement; finding stock in
 * the pool is worth saying, and is not the engine's decision to take. Every row states
 * both numbers so the choice can actually be made.
 */
export function CoveredByStockView({
  rows,
  isLoading,
  isError,
  error,
}: {
  rows: ReorderRecommendation[];
  isLoading: boolean;
  isError?: boolean;
  error?: unknown;
}) {
  if (isLoading) {
    return (
      <Card className="space-y-3 p-4">
        <Skeleton className="h-9 w-full" />
        <Skeleton className="h-9 w-full" />
        <Skeleton className="h-9 w-full" />
      </Card>
    );
  }

  if (isError) {
    return (
      <Card className="p-8 text-center text-sm text-muted-foreground">
        {error instanceof Error ? error.message : 'Failed to load these rows.'}
      </Card>
    );
  }

  if (!rows.length) {
    return (
      <Card className="p-8 text-center">
        <p className="text-sm font-medium">Nothing is waiting on that choice.</p>
        <p className="mt-1 text-2xs text-muted-foreground">
          Every committed line either needs a purchase or has already been decided.
        </p>
      </Card>
    );
  }

  return (
    <Card className="overflow-hidden">
      <CardHeader className="py-3">
        <h3 className="text-sm font-semibold">
          Covered by stock
          <span className="ms-2 text-2xs font-normal text-muted-foreground">
            {fmtInt(rows.length)} waiting on a decision
          </span>
        </h3>
      </CardHeader>
      <div className="overflow-x-auto">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>SKU</TableHead>
              <TableHead>Location</TableHead>
              <TableHead className="text-end">Committed</TableHead>
              <TableHead className="text-end">Available</TableHead>
              <TableHead className="text-end">Buy anyway</TableHead>
              <TableHead className="text-end">Cost to buy</TableHead>
              <TableHead>Why it is here</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {rows.map((r) => (
              <TableRow key={r.id}>
                <TableCell className="max-w-[200px] truncate font-medium" title={r.sku}>
                  {r.sku}
                  {/* The part of this demand nobody located. Said on the row because it is
                      the part most likely to be wrong. */}
                  {r.unlocated_demand ? (
                    <Badge variant="secondary" size="sm" className="ms-2 font-normal">
                      {fmtInt(r.unlocated_demand)} unlocated
                    </Badge>
                  ) : null}
                </TableCell>
                <TableCell className="whitespace-nowrap">{r.warehouse_code ?? '-'}</TableCell>
                <TableCell className="text-end tabular-nums">
                  {fmtInt(r.covered_committed ?? null)}
                </TableCell>
                <TableCell className="text-end tabular-nums">
                  {fmtInt(r.covered_available ?? null)}
                </TableCell>
                <TableCell className="text-end tabular-nums">{fmtInt(r.order_qty)}</TableCell>
                <TableCell className="text-end tabular-nums">
                  {r.cash_impact == null ? '-' : fmtMoney(r.cash_impact)}
                </TableCell>
                <TableCell
                  className="max-w-[280px] truncate text-2xs text-muted-foreground"
                  title={r.reason_label ?? undefined}
                >
                  {r.reason_label ?? '-'}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
    </Card>
  );
}

export default CoveredByStockView;
