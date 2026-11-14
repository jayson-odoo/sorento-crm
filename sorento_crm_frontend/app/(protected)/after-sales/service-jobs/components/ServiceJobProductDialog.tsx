'use client';

import { useEffect, useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import { DatePicker } from '@/components/ui/date-picker';
import { SearchableSelect, type SearchableSelectOption } from '@/components/common/SearchableSelect';
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { getKinds, testKindRules } from '../../warranty/services/warrantyConfigService';
import { useServiceJobProductMutations } from '../hooks/useServiceJobProducts';
import { getDefectOptions, searchCatalogueProducts } from '../services/serviceJobService';
import { codeWithName } from '@/lib/product-display';
import { ymd } from '../lib/jobDates';
import type { ServiceJobProduct } from '../types/serviceJob.types';

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  jobId: string;
  /** Present = Edit. */
  line?: ServiceJobProduct | null;
}

function parseYmd(value: string | null | undefined): Date | undefined {
  const [y, m, d] = (value ?? '').split('-').map(Number);
  return y && m && d ? new Date(y, m - 1, d) : undefined;
}

const productLabel = (p: { product_code: string; product_name: string }) => codeWithName(p.product_code, p.product_name);

export default function ServiceJobProductDialog({ open, onOpenChange, jobId, line }: Props) {
  const { add, update } = useServiceJobProductMutations(jobId);
  const [product, setProduct] = useState<SearchableSelectOption | null>(null);
  const [kindId, setKindId] = useState('');
  const [purchase, setPurchase] = useState<Date | undefined>();
  const [defectId, setDefectId] = useState('');
  const [filledFor, setFilledFor] = useState<string | null>(null);

  const { data: kinds } = useQuery({
    queryKey: ['warranty-kinds-select'],
    queryFn: () => getKinds({ pageIndex: 0, pageSize: 200, sorting: [{ id: 'name', desc: false }], searchQuery: '', is_active: ['true'] }),
    enabled: open,
    staleTime: 60_000,
  });
  const { data: defects = [] } = useQuery({
    queryKey: ['warranty-defect-types'],
    queryFn: getDefectOptions,
    enabled: open,
    staleTime: 60_000,
  });

  // What the form was last filled for: a refetched line is a new object for the same line.
  useEffect(() => {
    const key = open ? (line?.id ?? 'new') : null;
    if (key === filledFor) return;
    setFilledFor(key);
    if (!key) return;
    setProduct(line ? { value: line.product_id, label: productLabel({ product_code: line.product_code ?? '', product_name: line.product_name ?? '' }) } : null);
    setKindId(line?.kind_id ?? '');
    setPurchase(parseYmd(line?.purchase_date));
    setDefectId(line?.defect_type_id ?? '');
  }, [open, line, filledFor]);

  const kindOptions = useMemo(() => {
    const options = (kinds?.data ?? []).map((k) => ({ value: k.id, label: k.name }));
    // A line keeps a kind archived since, so it must still show.
    if (line?.kind_id && line.kind_name && !options.some((o) => o.value === line.kind_id)) {
      options.unshift({ value: line.kind_id, label: line.kind_name });
    }
    return options;
  }, [kinds, line]);

  const defectOptions = useMemo(() => {
    const options = defects.map((d) => ({ value: d.id, label: d.label }));
    if (line?.defect_type_id && line.defect_label && !options.some((o) => o.value === line.defect_type_id)) {
      options.unshift({ value: line.defect_type_id, label: line.defect_label });
    }
    return options;
  }, [defects, line]);

  // Static options widened by the server search: the pattern every other select in a dialog uses.
  const [productQuery, setProductQuery] = useState('');
  const { data: found = [] } = useQuery({
    queryKey: ['service-job-product-search', productQuery],
    queryFn: () => searchCatalogueProducts(productQuery),
    enabled: open && !line,
    staleTime: 30_000,
  });
  const productOptions = useMemo(() => {
    const options = found.map((p) => ({ value: p.id, label: productLabel(p) }));
    if (product && !options.some((o) => o.value === product.value)) options.unshift(product);
    return options;
  }, [found, product]);

  // Picking a product prefills the Kind the rules suggest; CS can change or clear it.
  const onProductPicked = async (option: SearchableSelectOption | null) => {
    setProduct(option);
    if (!option || line) return;
    try {
      const result = await testKindRules(option.value);
      setKindId(result.resolved_kind?.id ?? '');
    } catch {
      setKindId('');
    }
  };

  const pending = add.isPending || update.isPending;
  const canSave = line ? true : !!product;

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!canSave) return;
    const shared = {
      kind_id: kindId || null,
      purchase_date: purchase ? ymd(purchase) : null,
      defect_type_id: defectId || null,
    };
    try {
      if (line) await update.mutateAsync({ lineId: line.id, values: shared });
      else await add.mutateAsync({ product_id: (product as SearchableSelectOption).value, ...shared });
      onOpenChange(false);
    } catch {
      /* the mutation toasts the server's message */
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="overflow-hidden sm:max-w-lg" aria-describedby={undefined}>
        <DialogHeader>
          <DialogTitle>{line ? 'Edit product' : 'Add product'}</DialogTitle>
        </DialogHeader>
        <form onSubmit={submit} className="flex min-h-0 flex-1 flex-col gap-4">
          <DialogBody className="min-h-0 space-y-4 overflow-y-auto">
            <div className="space-y-1">
              <Label>Product</Label>
              {line ? (
                <p className="text-sm" title={product?.label}>{product?.label}</p>
              ) : (
                <SearchableSelect
                  value={product?.value ?? ''}
                  onChange={() => undefined}
                  onOptionChange={(o) => void onProductPicked(o)}
                  options={productOptions}
                  onSearchChange={setProductQuery}
                  placeholder="Search product code or description"
                  aria-label="Product"
                truncateTriggerLabel
                />
              )}
            </div>
            <div className="space-y-1">
              <Label>Kind</Label>
              <SearchableSelect
                value={kindId}
                onChange={setKindId}
                options={kindOptions}
                placeholder="Select kind"
                aria-label="Kind"
                clearable
              />
            </div>
            <div className="space-y-1">
              <Label>Purchase date</Label>
              <DatePicker value={purchase} onChange={setPurchase} ariaLabel="Purchase date" portal />
            </div>
            <div className="space-y-1">
              <Label>Defect</Label>
              <SearchableSelect
                value={defectId}
                onChange={setDefectId}
                options={defectOptions}
                placeholder="Select defect"
                aria-label="Defect"
                clearable
              />
            </div>
          </DialogBody>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit" disabled={!canSave || pending}>
              {line ? 'Save' : 'Add product'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
