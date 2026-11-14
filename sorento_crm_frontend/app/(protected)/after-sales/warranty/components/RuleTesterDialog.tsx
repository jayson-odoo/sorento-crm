'use client';

import { useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import { SearchableSelect, type SearchableSelectOption } from '@/components/common/SearchableSelect';
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { searchCatalogueProducts } from '../../service-jobs/services/serviceJobService';
import { useTestKindRules } from '../hooks/useWarrantyConfig';
import { formatMatchTypeLabel } from '../lib/warrantyLabels';
import type { KindRuleTestResult } from '../types/warranty.types';
import { codeWithName } from '@/lib/product-display';

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function RuleTesterDialog({ open, onOpenChange }: Props) {
  const test = useTestKindRules();
  const [product, setProduct] = useState<SearchableSelectOption | null>(null);
  const [result, setResult] = useState<KindRuleTestResult | null>(null);

  // Static options widened by the server search: the pattern every other select in a dialog uses.
  const [query, setQuery] = useState('');
  const { data: found = [] } = useQuery({
    queryKey: ['rule-tester-product-search', query],
    queryFn: () => searchCatalogueProducts(query),
    enabled: open,
    staleTime: 30_000,
  });
  const options = useMemo(() => {
    const list = found.map((p) => ({ value: p.id, label: codeWithName(p.product_code, p.product_name) }));
    if (product && !list.some((o) => o.value === product.value)) list.unshift(product);
    return list;
  }, [found, product]);

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
      <DialogContent className="overflow-hidden sm:max-w-md" aria-describedby={undefined}>
        <DialogHeader>
          <DialogTitle>Test a product</DialogTitle>
        </DialogHeader>
        <DialogBody className="min-h-0 space-y-4 overflow-y-auto">
          <div className="space-y-1">
            <Label>Product</Label>
            <SearchableSelect
              value={product?.value ?? ''}
              onChange={() => undefined}
              onOptionChange={(o) => void pick(o)}
              options={options}
              onSearchChange={setQuery}
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
