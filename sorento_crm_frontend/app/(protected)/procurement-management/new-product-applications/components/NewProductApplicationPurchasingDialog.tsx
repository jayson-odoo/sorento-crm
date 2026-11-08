'use client';

/**
 * Purchasing's one dialog on an Approved / Completed application, like the stock inquiry's "Edit
 * purchasing response": the answer on the new product code (link an existing one, type a new one,
 * or not opening), the lead time and the cost, saved in one PUT. A key that did not change is not
 * sent, so saving the lead time alone never touches the answer.
 */

import { useState } from 'react';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { NumberInput } from '@/components/ui/number-input';
import { RadioGroup, RadioGroupItem } from '@/components/ui/radio-group';
import { SearchableSelect } from '@/components/common/SearchableSelect';
import { Textarea } from '@/components/ui/textarea';
import { numberFieldError } from '@/lib/number-field';
import { codeWithName } from '@/lib/product-display';
import type {
  NewProductApplicationDetail as Detail,
  NewProductApplicationPurchasingResponseWrite as Write,
} from '@/types/newProductApplication';
import { useNewProductApplicationMutations } from '../hooks/useNewProductApplications';
import { searchNewProductApplicationProducts } from '../services/newProductApplicationService';

type Outcome = 'link' | 'new' | 'none';

const figure = (v: string | number | null | undefined) =>
  v === null || v === undefined ? '' : String(v);

const savedOutcome = (r: Detail): Outcome | null =>
  r.new_product_id ? 'link' : r.new_code_text ? 'new' : null;

export default function NewProductApplicationPurchasingDialog({
  application: r,
  onClose,
}: {
  application: Detail;
  onClose: () => void;
}) {
  const { purchasingResponse } = useNewProductApplicationMutations();
  const initial = savedOutcome(r);
  const initialProduct = r.new_product_id
    ? {
        value: r.new_product_id,
        label: r.new_product_code ?? '',
      }
    : null;
  const [outcome, setOutcome] = useState<Outcome | null>(initial);
  const [product, setProduct] = useState(initialProduct);
  const [newCode, setNewCode] = useState(r.new_code_text ?? '');
  const [leadTime, setLeadTime] = useState(r.lead_time ?? '');
  const [cost, setCost] = useState(figure(r.cost_price));
  const [lineCosts, setLineCosts] = useState<Record<string, string>>(
    Object.fromEntries(r.lines.map((l) => [l.id, figure(l.cost_price)])),
  );
  const [error, setError] = useState<string | null>(null);
  const earlier = r.suggestions?.[0];

  const searchProducts = async (q: string) =>
    (await searchNewProductApplicationProducts(q)).map((h) => ({
      value: h.id,
      label: h.product_code,
      description: h.product_name,
    }));

  const save = async () => {
    const costs = r.lines.length
      ? r.lines.map((l) => lineCosts[l.id] ?? '')
      : [cost];
    if (costs.some((c) => numberFieldError(c, { min: 0, optional: true }))) {
      setError('Cost must be 0 or more.');
      return;
    }
    if (outcome === 'link' && !product) {
      setError('Pick the product code to link.');
      return;
    }
    if (outcome === 'new' && !newCode.trim()) {
      setError('Enter the new product code.');
      return;
    }
    const body: Write = { lead_time: leadTime.trim() || null };
    if (r.lines.length) {
      body.lines = r.lines.map((l) => ({
        id: l.id,
        cost_price: (lineCosts[l.id] ?? '').trim() || null,
      }));
    } else {
      body.cost_price = cost.trim() || null;
    }
    // The answer is sent only when it was chosen or changed.
    if (
      outcome === 'link' &&
      (initial !== 'link' || product?.value !== r.new_product_id)
    ) {
      body.outcome = 'link';
      body.product_id = product?.value;
    } else if (
      outcome === 'new' &&
      (initial !== 'new' || newCode.trim() !== (r.new_code_text ?? ''))
    ) {
      body.outcome = 'new';
      body.new_code = newCode.trim();
    }
    if (outcome === 'none') body.outcome = null;
    setError(null);
    try {
      await purchasingResponse.mutateAsync({ id: r.id, data: body });
      onClose();
    } catch {
      // the mutation's own onError toast names the refusal
    }
  };

  const saving = purchasingResponse.isPending;

  return (
    <Dialog open onOpenChange={(next) => !next && onClose()}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Edit purchasing response</DialogTitle>
          <DialogDescription className="sr-only">
            Purchasing response for {r.application_no}
          </DialogDescription>
        </DialogHeader>
        <DialogBody className="space-y-4">
          {earlier && (
            <div className="flex flex-wrap items-center gap-1.5 text-sm">
              <span className="min-w-0 break-words">
                Created before: <b>{earlier.product_code}</b>
                {earlier.application_no ? ` (${earlier.application_no})` : ''}
              </span>
              <Button
                type="button"
                size="sm"
                variant="outline"
                onClick={() => {
                  // A typed code AutoCount has not sent has no product to link: it fills New product code.
                  if (earlier.product_id) {
                    setOutcome('link');
                    setProduct({
                      value: earlier.product_id,
                      label: earlier.product_code,
                    });
                  } else {
                    setOutcome('new');
                    setNewCode(earlier.product_code);
                  }
                }}
              >
                Use {earlier.product_code}
              </Button>
            </div>
          )}

          <RadioGroup
            value={outcome ?? ''}
            onValueChange={(v) => setOutcome(v as Outcome)}
            aria-label="New product code"
            className="gap-3"
          >
            <div className="space-y-2">
              <div className="flex items-center gap-2">
                <RadioGroupItem value="link" id="npa-out-link" />
                <Label htmlFor="npa-out-link">
                  Link an existing product code
                </Label>
              </div>
              {outcome === 'link' && (
                <SearchableSelect
                  aria-label="Product code"
                  value={product?.value ?? ''}
                  placeholder="Search product code"
                  emptyMessage="No product matches that."
                  fetchOptions={searchProducts}
                  selectedOption={product ?? undefined}
                  onChange={() => undefined}
                  onOptionChange={(opt) =>
                    setProduct(
                      opt ? { value: opt.value, label: opt.label } : null,
                    )
                  }
                />
              )}
            </div>
            <div className="space-y-2">
              <div className="flex items-center gap-2">
                <RadioGroupItem value="new" id="npa-out-new" />
                <Label htmlFor="npa-out-new">New product code</Label>
              </div>
              {outcome === 'new' && (
                <Input
                  aria-label="New product code"
                  value={newCode}
                  maxLength={100}
                  onChange={(e) => setNewCode(e.target.value)}
                />
              )}
            </div>
            {initial !== null && (
              <div className="flex items-center gap-2">
                <RadioGroupItem value="none" id="npa-out-none" />
                <Label htmlFor="npa-out-none">No answer yet</Label>
              </div>
            )}
          </RadioGroup>

          <div className="space-y-1.5">
            <Label htmlFor="npa-lead-time">Lead time</Label>
            <Input
              id="npa-lead-time"
              value={leadTime}
              onChange={(e) => setLeadTime(e.target.value)}
            />
          </div>

          {r.lines.length ? (
            <div className="space-y-2">
              {r.lines.map((l, i) => (
                <div key={l.id} className="space-y-1.5">
                  <Label htmlFor={`npa-cost-${l.id}`}>
                    Cost for product {i + 1}
                    {l.description || l.proposed_code
                      ? ` (${codeWithName(l.proposed_code, l.description)})`
                      : ''}
                  </Label>
                  <NumberInput
                    id={`npa-cost-${l.id}`}
                    inputMode="decimal"
                    step="any"
                    aria-label={`Cost for product ${i + 1}`}
                    value={lineCosts[l.id] ?? ''}
                    onChange={(e) =>
                      setLineCosts((prev) => ({
                        ...prev,
                        [l.id]: e.target.value,
                      }))
                    }
                  />
                </div>
              ))}
            </div>
          ) : (
            <div className="space-y-1.5">
              <Label htmlFor="npa-cost">Cost (MYR)</Label>
              <NumberInput
                id="npa-cost"
                inputMode="decimal"
                step="any"
                aria-label="Cost (MYR)"
                value={cost}
                onChange={(e) => setCost(e.target.value)}
              />
            </div>
          )}
          {error && <p className="text-sm text-destructive">{error}</p>}
        </DialogBody>
        <DialogFooter className="flex-col gap-2 sm:flex-row sm:justify-end">
          <Button variant="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button disabled={saving} onClick={() => void save()}>
            {saving ? 'Saving...' : 'Save'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
