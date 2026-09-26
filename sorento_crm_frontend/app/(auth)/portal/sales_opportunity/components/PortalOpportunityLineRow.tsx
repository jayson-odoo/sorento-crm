'use client';

/**
 * One editable product line (UAC S2-16) - shared by `SalesOpportunityPortalForm` (create) and
 * `SalesOpportunityPortalDetail` (edit in place, Phase 3 fix2 should-fix 5), the portal's own
 * mirror of the CRM's `app/(protected)/sales/opportunities/components/OpportunityLineRow.tsx`.
 */
import { Trash2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { AsyncCombobox } from '../../components/AsyncCombobox';
import { getPortalProductOptions, type PortalProductOption } from '../../lib/sales-opportunity-service';

export interface LineDraft {
  key: string;
  productId: string;
  productLabel: string;
  qty: string;
}

let lineKeySeq = 0;
export function nextLineKey(): string {
  lineKeySeq += 1;
  return `line-${lineKeySeq}`;
}

export function PortalOpportunityLineRow({
  line,
  onChange,
  onRemove,
}: {
  line: LineDraft;
  onChange: (patch: Partial<LineDraft>) => void;
  onRemove: () => void;
}) {
  return (
    <div className="flex items-end gap-2">
      <div className="flex-1 flex flex-col gap-1.5">
        <Label htmlFor={`product-${line.key}`}>Product</Label>
        <AsyncCombobox<PortalProductOption>
          id={`product-${line.key}`}
          value={line.productLabel}
          onChange={(_v, item) =>
            onChange({
              productId: item?.id ?? '',
              productLabel: item ? `${item.code} - ${item.name ?? ''}` : '',
            })
          }
          fetchOptions={(q) => getPortalProductOptions(q)}
          optionValue={(o) => o.code}
          optionLabel={(o) => `${o.code} - ${o.name ?? ''}`}
          placeholder="Search products..."
        />
      </div>
      <div className="w-20 flex flex-col gap-1.5">
        <Label htmlFor={`qty-${line.key}`}>Qty</Label>
        <Input
          id={`qty-${line.key}`}
          type="number"
          min="0.01"
          step="0.01"
          value={line.qty}
          onChange={(e) => onChange({ qty: e.target.value })}
        />
      </div>
      <Button type="button" variant="ghost" size="sm" aria-label="Remove product" onClick={onRemove}>
        <Trash2 className="size-4" />
        Remove
      </Button>
    </div>
  );
}
