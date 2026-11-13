'use client';

import { useState } from 'react';
import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import { SearchableSelect, type SearchableSelectOption } from '@/components/common/SearchableSelect';
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { searchCatalogueProducts } from '../../service-jobs/services/serviceJobService';
import { useTestKindRules } from '../hooks/useWarrantyConfig';
import { formatMatchTypeLabel } from '../lib/warrantyLabels';
import type { KindRuleTestResult } from '../types/warranty.types';

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function RuleTesterDialog({ open, onOpenChange }: Props) {
  const test = useTestKindRules();
  const [product, setProduct] = useState<SearchableSelectOption | null>(null);
  const [result, setResult] = useState<KindRuleTestResult | null>(null);

  const fetchProducts = async (query: string): Promise<SearchableSelectOption[]> =>
    (await searchCatalogueProducts(query)).map((p) => ({
      value: p.id,
      label: `${p.product_code} ${p.product_name}`.trim(),
    }));

  const pick = async (option: SearchableSelectOption | null) => {
    setProduct(option);
    setResult(null);
    if (!option) return;
    try {
      setResult(await test.mutateAsync(option.value));
    } catch {
      /* the mutation toasts the server's message */
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="overflow-hidden sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Test a product</DialogTitle>
          <DialogDescription className="sr-only">See which kind the rules give a product.</DialogDescription>
        </DialogHeader>
        <DialogBody className="min-h-0 space-y-4 overflow-y-auto">
          <div className="space-y-1">
            <Label>Product</Label>
            <SearchableSelect
              value={product?.value ?? ''}
              onChange={() => undefined}
              onOptionChange={(o) => void pick(o)}
              fetchOptions={fetchProducts}
              selectedOption={product ?? undefined}
              placeholder="Search product code or description"
              aria-label="Product"
              truncateTriggerLabel
            />
          </div>
          {result &&
            (result.resolved_kind && result.deciding_rule ? (
              <dl className="grid grid-cols-[6rem_1fr] gap-2 text-sm">
                <dt className="text-muted-foreground">Kind</dt>
                <dd className="min-w-0 break-words">{result.resolved_kind.name}</dd>
                <dt className="text-muted-foreground">Rule</dt>
                <dd className="min-w-0 break-words">
                  <span>{formatMatchTypeLabel(result.deciding_rule.match_type)}</span>{' '}
                  <span>{result.deciding_rule.match_value}</span>
                </dd>
              </dl>
            ) : (
              <p className="text-sm">No warranty rule for this product yet</p>
            ))}
        </DialogBody>
        <DialogFooter>
          <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
            Close
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
