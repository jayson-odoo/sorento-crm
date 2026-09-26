'use client';

import { useEffect, useMemo, useState } from 'react';
import { LoaderCircleIcon, Plus, X } from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { SearchableSelect, type SearchableSelectOption } from '@/components/common/SearchableSelect';
import {
  getSalesOpportunityCustomerOptions,
  getSalesOpportunityProductOptions,
} from '../services/salesOpportunityService';
import { useSaveSalesOpportunity } from '../hooks/useSalesOpportunities';

const PROSPECT_PREFIX = 'prospect:';
const BLOCKED_VALUE = '__blocked__';

let lineKeySeq = 0;
function nextLineKey(): string {
  lineKeySeq += 1;
  return `line-${lineKeySeq}`;
}

interface LineDraft {
  key: string;
  productId: string;
  qty: string;
}

/**
 * One product line's own picker. `options` (not `fetchOptions`) so this row's search box
 * is one control, not two - `onSearchChange` still hits the server on every keystroke
 * (LESSONS-LEARNT: never a capped static list over the ~22,000-product catalog).
 */
function ProductLineRow({
  line,
  onChange,
  onRemove,
}: {
  line: LineDraft;
  onChange: (patch: Partial<LineDraft>) => void;
  onRemove: () => void;
}) {
  const [options, setOptions] = useState<SearchableSelectOption[]>([]);

  useEffect(() => {
    let active = true;
    getSalesOpportunityProductOptions('').then((opts) => {
      if (active) setOptions(opts);
    });
    return () => {
      active = false;
    };
  }, []);

  return (
    <div data-testid="opportunity-line-row" className="flex items-end gap-2">
      <div className="flex-1 flex flex-col gap-1.5">
        <Label htmlFor={`Product-${line.key}`}>Product</Label>
        <SearchableSelect
          id={`Product-${line.key}`}
          value={line.productId}
          onChange={(v) => onChange({ productId: v })}
          options={options}
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

/**
 * The Log opportunity modal (UAC S2-12, S2-15, S2-16; plan 3.4, 3.5, section 16, N10, N11).
 *
 * ONE "Customer or prospect" search (N10): typing lists matching customers, plus, when
 * nothing matches the typed name exactly, an "Add ... as a new prospect" option; a name
 * that belongs to another agent's customer shows as a disabled, explained option instead
 * (S2-15). Products are optional (N11): a product and a quantity per row, the complaint
 * form's line pattern. Create only - editing is in place on the detail page.
 */
export default function SalesOpportunityModal({
  open,
  onOpenChange,
  presetCustomerId,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Preset from a customer's own page (J8); the field still shows the picked customer. */
  presetCustomerId?: string;
}) {
  const save = useSaveSalesOpportunity();

  const [customerOrProspect, setCustomerOrProspect] = useState('');
  const [title, setTitle] = useState('');
  const [expectedAmount, setExpectedAmount] = useState('');
  const [expectedCloseDate, setExpectedCloseDate] = useState('');
  const [lines, setLines] = useState<LineDraft[]>([]);

  useEffect(() => {
    if (!open) return;
    setCustomerOrProspect(presetCustomerId ?? '');
    setTitle('');
    setExpectedAmount('');
    setExpectedCloseDate('');
    setLines([]);
  }, [open, presetCustomerId]);

  const customerOptions = useMemo(
    () => [] as SearchableSelectOption[],
    [],
  );

  const fetchCustomerOptions = async (query: string): Promise<SearchableSelectOption[]> => {
    const result = await getSalesOpportunityCustomerOptions(query);
    const options: SearchableSelectOption[] = result.items.map((item) => ({
      value: item.customer_id,
      label: `${item.customer_code} - ${item.customer_name}`,
    }));
    if (result.blocked) {
      options.push({ value: BLOCKED_VALUE, label: result.blocked.message, disabled: true });
    } else if (result.prospect) {
      options.push({
        value: `${PROSPECT_PREFIX}${result.prospect.name}`,
        label: `Add "${result.prospect.name}" as a new prospect`,
      });
    }
    return options;
  };

  const addLine = () => setLines((prev) => [...prev, { key: nextLineKey(), productId: '', qty: '1' }]);
  const removeLine = (key: string) => setLines((prev) => prev.filter((l) => l.key !== key));
  const updateLine = (key: string, patch: Partial<LineDraft>) =>
    setLines((prev) => prev.map((l) => (l.key === key ? { ...l, ...patch } : l)));

  const isProspect = customerOrProspect.startsWith(PROSPECT_PREFIX);
  // Customer-or-prospect validity (including the exact-name-match rules, S2-15) stays
  // server-authoritative - the hook's onError toasts a 422 the same way any other save
  // failure does, so it is not duplicated here. Blocked is the one client-side rule
  // clearly enforceable without a round trip: it is never a submittable choice at all.
  const canSave =
    customerOrProspect !== BLOCKED_VALUE &&
    title.trim().length > 0 &&
    !!expectedAmount &&
    !!expectedCloseDate &&
    !save.isPending;

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!canSave) return;
    const payload = {
      title: title.trim(),
      expected_amount: expectedAmount,
      expected_close_date: expectedCloseDate,
      ...(isProspect
        ? { prospect_name: customerOrProspect.slice(PROSPECT_PREFIX.length) }
        : { customer_id: customerOrProspect }),
      lines: lines
        .filter((l) => l.productId)
        .map((l) => ({ product_id: l.productId, qty: Number(l.qty) || 0 })),
    };
    try {
      await save.mutateAsync(payload);
      onOpenChange(false);
    } catch {
      // The hook toasted the reason; the modal stays open with what was typed.
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Log opportunity</DialogTitle>
        </DialogHeader>
        <form onSubmit={submit} className="flex flex-col gap-4">
          <DialogBody className="flex flex-col gap-4">
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="opportunity-customer">Customer or prospect</Label>
              <SearchableSelect
                id="opportunity-customer"
                aria-label="Customer or prospect"
                value={customerOrProspect}
                onChange={setCustomerOrProspect}
                options={customerOptions}
                fetchOptions={fetchCustomerOptions}
                placeholder="Search customers..."
                wrapOptions
              />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="opportunity-title">Title</Label>
              <Input
                id="opportunity-title"
                value={title}
                maxLength={200}
                onChange={(e) => setTitle(e.target.value)}
              />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="opportunity-amount">Expected amount</Label>
              <Input
                id="opportunity-amount"
                type="number"
                min="0"
                step="0.01"
                value={expectedAmount}
                onChange={(e) => setExpectedAmount(e.target.value)}
              />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="opportunity-close-date">Expected close date</Label>
              <Input
                id="opportunity-close-date"
                type="date"
                value={expectedCloseDate}
                onChange={(e) => setExpectedCloseDate(e.target.value)}
              />
            </div>
            <div className="flex flex-col gap-2">
              <div className="flex items-center justify-between">
                <Label>Products</Label>
                <Button type="button" variant="outline" size="sm" onClick={addLine}>
                  <Plus className="size-3.5" />
                  Add product
                </Button>
              </div>
              {lines.length === 0 ? (
                <p className="text-sm text-muted-foreground">No products yet</p>
              ) : (
                <div className="flex flex-col gap-2">
                  {lines.map((line) => (
                    <ProductLineRow
                      key={line.key}
                      line={line}
                      onChange={(patch) => updateLine(line.key, patch)}
                      onRemove={() => removeLine(line.key)}
                    />
                  ))}
                </div>
              )}
            </div>
          </DialogBody>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit" disabled={!canSave}>
              {save.isPending ? <LoaderCircleIcon className="size-4 animate-spin" /> : null}
              Save
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
