'use client';

/**
 * One product line's own picker (plan section 16, N11) - shared by `SalesOpportunityModal`
 * (create) and `SalesOpportunityDetail` (edit in place, Phase 3 fix B2), so the two never
 * carry two copies of the same product-row behaviour.
 */
import { useEffect, useMemo, useState } from 'react';
import { X } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { SearchableSelect, type SearchableSelectOption } from '@/components/common/SearchableSelect';
import { getSalesOpportunityProductOptions } from '../services/salesOpportunityService';

let lineKeySeq = 0;
export function nextLineKey(): string {
  lineKeySeq += 1;
  return `line-${lineKeySeq}`;
}

export interface LineDraft {
  key: string;
  productId: string;
  qty: string;
  /** An existing line's own label (edit in place, Phase 3 fix B2) - seeds the row's
   *  "keep the picked option" state so an already-saved line shows its product
   *  immediately, rather than only once a fetch happens to include it. */
  productLabel?: string;
}

/**
 * `options` (not `fetchOptions`) so this row's search box is one control, not two -
 * `onSearchChange` still hits the server on every keystroke (LESSONS-LEARNT: never a capped
 * static list over the ~22,000-product catalog).
 */
export function OpportunityLineRow({
  line,
  onChange,
  onRemove,
}: {
  line: LineDraft;
  onChange: (patch: Partial<LineDraft>) => void;
  onRemove: () => void;
}) {
  const [options, setOptions] = useState<SearchableSelectOption[]>([]);
  // Reviewer should-fix 7: a later search REPLACES `options` wholesale, and a picked
  // product from an earlier search is gone from that replacement the moment the reader
  // types again - the trigger would then find no match for `line.productId` and fall
  // back to the placeholder, reading as if the pick had been lost. Keeping the chosen
  // option itself, merged back in, means it survives regardless of what the next search
  // returns (the static-mode equivalent of `selectedOption`, which only applies in
  // `fetchOptions` mode).
  const [selected, setSelected] = useState<SearchableSelectOption | null>(
    line.productId && line.productLabel ? { value: line.productId, label: line.productLabel } : null,
  );

  useEffect(() => {
    let active = true;
    getSalesOpportunityProductOptions('').then((opts) => {
      if (active) setOptions(opts);
    });
    return () => {
      active = false;
    };
  }, []);

  const mergedOptions = useMemo(() => {
    if (!selected || options.some((o) => o.value === selected.value)) return options;
    return [selected, ...options];
  }, [options, selected]);

  return (
    <div data-testid="opportunity-line-row" className="flex items-end gap-2">
      <div className="flex-1 flex flex-col gap-1.5">
        <Label htmlFor={`Product-${line.key}`}>Product</Label>
        <SearchableSelect
          id={`Product-${line.key}`}
          value={line.productId}
          onChange={(v) => onChange({ productId: v })}
          onOptionChange={setSelected}
          options={mergedOptions}
          onSearchChange={(q) => getSalesOpportunityProductOptions(q).then(setOptions)}
          placeholder="Search products..."
          wrapOptions
        />
      </div>
      <div className="w-24 flex flex-col gap-1.5">
        <Label htmlFor={`Qty-${line.key}`}>Qty</Label>
        <Input
          id={`Qty-${line.key}`}
          type="number"
          min="0.01"
          step="0.01"
          value={line.qty}
          onChange={(e) => onChange({ qty: e.target.value })}
        />
      </div>
      <Button type="button" variant="ghost" size="sm" aria-label="Remove line" onClick={onRemove}>
        <X className="size-4" />
        Remove
      </Button>
    </div>
  );
}
