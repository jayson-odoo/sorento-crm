'use client';

import { useState } from 'react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardHeader, CardHeading, CardTitle } from '@/components/ui/card';
import { useUnmatchedSupplierCodes } from '../../hooks/useSupplierCodeAliases';
import { MatchToProductDialog } from '../../components/MatchToProductDialog';
import { EM_DASH, fmtInt } from '../../lib/format';

/**
 * The codes this supplier sent that bind to nothing we hold (R16).
 *
 * Rendered on the loading plan because that is where the consequence lands: a stock row with
 * no product is stock the plan cannot offer, so a supplier can be holding 400 pieces of
 * something and the plan shows nothing. The upload dialog counts them and goes away; this is
 * where somebody comes back and answers them.
 *
 * Hidden when there are none - it is not a section of the record, it is a queue, and an
 * empty queue on screen every day is noise the eye learns to skip.
 */
export function UnmatchedSupplierCodesPanel({
  supplierId,
  supplierName,
}: {
  supplierId: string;
  supplierName?: string | null;
}) {
  const { data: rows = [] } = useUnmatchedSupplierCodes(supplierId || null);
  const [matching, setMatching] = useState<{ code: string; label: string | null } | null>(
    null,
  );

  if (rows.length === 0) return null;

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between gap-3 py-3">
        <CardHeading>
          <CardTitle className="text-sm">
            {rows.length === 1
              ? '1 code matches nothing we hold'
              : `${rows.length} codes match nothing we hold`}
          </CardTitle>
        </CardHeading>
        <Badge variant="secondary" appearance="light">
          {fmtInt(rows.reduce((sum, r) => sum + (r.qty_packed || 0), 0))} packed
        </Badge>
      </CardHeader>
      <div className="divide-y divide-border">
        {rows.map((row) => (
          <div
            key={row.item_code}
            className="flex flex-col gap-1 p-3 sm:flex-row sm:items-center sm:justify-between"
          >
            <div className="min-w-0">
              <p className="truncate text-sm font-medium" title={row.item_code}>
                {row.item_code}
              </p>
              <p className="truncate text-2xs text-muted-foreground">
                {[row.product_name, row.brand, row.spec].filter(Boolean).join(' · ') ||
                  EM_DASH}
                {row.qty_packed ? ` · ${fmtInt(row.qty_packed)} packed` : ''}
              </p>
            </div>
            <Button
              variant="outline"
              size="sm"
              className="shrink-0"
              onClick={() =>
                setMatching({ code: row.item_code, label: row.product_name })
              }
            >
              Match to product
            </Button>
          </div>
        ))}
      </div>

      <MatchToProductDialog
        open={!!matching}
        onOpenChange={(o) => !o && setMatching(null)}
        supplierId={supplierId}
        supplierCode={matching?.code ?? null}
        supplierLabel={matching?.label ?? supplierName ?? null}
        onMatched={() => setMatching(null)}
      />
    </Card>
  );
}

export default UnmatchedSupplierCodesPanel;
