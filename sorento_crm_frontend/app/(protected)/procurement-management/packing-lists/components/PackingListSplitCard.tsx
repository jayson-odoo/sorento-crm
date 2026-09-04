'use client';

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { useConsolidatedPackingList } from '@/app/(protected)/scm/hooks/useFulfilment';
import { computeCompanySplit, type CompanySplitRow } from './packingListLineMath';

const EM_DASH = '-';

const moneyFmt = new Intl.NumberFormat('en-MY', {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});
const cbmFmt = new Intl.NumberFormat('en-MY', {
  minimumFractionDigits: 3,
  maximumFractionDigits: 3,
});

function fmtMoney(value: number | null): string {
  return value === null ? EM_DASH : moneyFmt.format(value);
}

function fmtCbm(value: number): string {
  return cbmFmt.format(value);
}

/**
 * What each company owes on this container, per the same ratios the export's footer writes
 * (AC-G4): clearance and China freight follow CBM share, insurance follows amount share.
 *
 * Fed by `GET /inbound-shipments/{id}/packing-list` - the same JSON `build()` the download
 * uses - so a number here and the cell Download writes cannot drift apart (S7 ruling 3).
 */
export function PackingListSplitCard({ packingListId }: { packingListId: string | null }) {
  const { data, isLoading, isError, error } = useConsolidatedPackingList(packingListId);

  if (!packingListId) return null;

  return (
    <Card>
      <CardHeader>
        <CardTitle>Split</CardTitle>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <Skeleton className="h-24 w-full rounded-lg" />
        ) : isError ? (
          <p className="text-sm text-muted-foreground">
            {error instanceof Error ? error.message : 'Failed to load the split.'}
          </p>
        ) : !data || !data.factories.length ? (
          <p className="text-sm text-muted-foreground">
            No shipment lines yet, so there is nothing to split between the companies.
          </p>
        ) : (
          <SplitTable data={data} />
        )}
      </CardContent>
    </Card>
  );
}

function SplitTable({
  data,
}: {
  data: NonNullable<ReturnType<typeof useConsolidatedPackingList>['data']>;
}) {
  const split = computeCompanySplit(data);

  const totalRow: CompanySplitRow = {
    company: 'SORENTO',
    cbm: split.totalCbm,
    amount: split.totalAmount,
    clearance: split.totalClearance,
    insurance: split.totalInsurance,
    chinaFreight: split.totalChinaFreight,
  };

  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[560px] text-sm">
        <thead>
          <tr className="border-b text-start text-xs text-muted-foreground">
            <th className="py-2 text-start font-medium">Company</th>
            <th className="py-2 text-end font-medium">CBM</th>
            <th className="py-2 text-end font-medium">Clearance</th>
            <th className="py-2 text-end font-medium">Insurance</th>
            <th className="py-2 text-end font-medium">China freight</th>
            <th className="py-2 text-end font-medium">Amount</th>
          </tr>
        </thead>
        <tbody>
          {split.rows.map((row) => (
            <tr key={row.company} className="border-b last:border-b-0">
              <td className="py-2 font-medium">{row.company}</td>
              <td className="py-2 text-end tabular-nums">{fmtCbm(row.cbm)}</td>
              <td className="py-2 text-end tabular-nums">{fmtMoney(row.clearance)}</td>
              <td className="py-2 text-end tabular-nums">{fmtMoney(row.insurance)}</td>
              <td className="py-2 text-end tabular-nums">{fmtMoney(row.chinaFreight)}</td>
              <td className="py-2 text-end tabular-nums">{fmtMoney(row.amount)}</td>
            </tr>
          ))}
        </tbody>
        <tfoot>
          <tr className="font-semibold">
            <td className="py-2">Total</td>
            <td className="py-2 text-end tabular-nums">{fmtCbm(totalRow.cbm)}</td>
            <td className="py-2 text-end tabular-nums">{fmtMoney(totalRow.clearance)}</td>
            <td className="py-2 text-end tabular-nums">{fmtMoney(totalRow.insurance)}</td>
            <td className="py-2 text-end tabular-nums">{fmtMoney(totalRow.chinaFreight)}</td>
            <td className="py-2 text-end tabular-nums">{fmtMoney(totalRow.amount)}</td>
          </tr>
        </tfoot>
      </table>
    </div>
  );
}

export default PackingListSplitCard;
