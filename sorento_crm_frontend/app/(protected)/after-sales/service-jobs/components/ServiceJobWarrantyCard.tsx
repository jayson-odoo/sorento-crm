import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { formatCivilDate } from '../../warranty/lib/warrantyLabels';
import type { WarrantyLine } from '../types/serviceJob.types';
import WarrantyPill from './WarrantyPill';

const HEADS: { title: string; className: string }[] = [
  { title: 'Product', className: 'w-56' },
  { title: 'Part', className: 'w-40' },
  { title: 'Answer', className: 'w-36' },
  { title: 'Until', className: 'w-28' },
  { title: 'Reason', className: 'w-80' },
];

function Cell({ value }: { value: string | null | undefined }) {
  return (
    <span className="block truncate" title={value || undefined}>
      {value || '-'}
    </span>
  );
}

/** What the policy says about each product on the job: one row per product and term. Pure props. */
export default function ServiceJobWarrantyCard({ warranty }: { warranty: WarrantyLine[] }) {
  const rows = warranty.flatMap((line) =>
    line.verdicts.map((v, i) => ({
      key: `${line.id}-${i}`,
      product: [line.product_code, line.product_name].filter(Boolean).join(' '),
      verdict: v,
    })),
  );
  return (
    <Card>
      <CardHeader>
        <CardTitle>Warranty</CardTitle>
      </CardHeader>
      <CardContent>
        {rows.length === 0 ? (
          <div className="py-6 text-center">
            <h3 className="text-sm font-medium">No warranty answers</h3>
            <p className="mt-1 text-sm text-muted-foreground">Add a product to see what the policy covers.</p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[40rem] table-fixed text-sm">
              <thead>
                <tr className="border-b text-left text-muted-foreground">
                  {HEADS.map((h) => (
                    <th key={h.title} className={`${h.className} px-2 py-2 font-medium`}>
                      {h.title}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {rows.map(({ key, product, verdict: v }) => (
                  <tr key={key} className="border-b last:border-0">
                    <td className="px-2 py-2"><Cell value={product} /></td>
                    <td className="px-2 py-2"><Cell value={v.part_name} /></td>
                    <td className="px-2 py-2"><WarrantyPill code={v.verdict} /></td>
                    <td className="px-2 py-2"><Cell value={v.expiry ? formatCivilDate(v.expiry) : null} /></td>
                    <td className="px-2 py-2"><Cell value={v.reason} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
