'use client';

import { useState } from 'react';
import { LoaderCircleIcon, Plus, Trash2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { toast } from '@/lib/toast';
import { AsyncCombobox } from '../../components/AsyncCombobox';
import {
  createPortalSalesOpportunity,
  getPortalCustomerOptions,
  getPortalProductOptions,
  type PortalProductOption,
} from '../../lib/sales-opportunity-service';

const PROSPECT_PREFIX = 'prospect:';
const BLOCKED_ID = '__blocked__';

interface CustomerComboOption {
  id: string;
  label: string;
  disabled?: boolean;
  customerId?: string;
  prospectName?: string;
}

interface LineDraft {
  key: string;
  productId: string;
  productLabel: string;
  qty: string;
}

let lineKeySeq = 0;
function nextLineKey(): string {
  lineKeySeq += 1;
  return `line-${lineKeySeq}`;
}

/**
 * The portal Sales Opportunity form (UAC S2-10, S2-15, S2-16; plan 3.5, N10, N11).
 *
 * The same "Customer or prospect" search and Products table contract as the CRM modal, over
 * the portal's own service and `AsyncCombobox` (the complaint form's product-line pattern).
 * No agent field anywhere - the agent comes from the token, never the form.
 */
export default function SalesOpportunityPortalForm({
  onCreated,
}: {
  /** Called with the new opportunity's id once the server confirms it - the caller (the
   *  `new` page) owns navigating away, so this component stays router-agnostic and testable
   *  without mocking `next/navigation`. */
  onCreated?: (id: string) => void;
}) {
  const [customerValue, setCustomerValue] = useState('');
  const [customerId, setCustomerId] = useState<string | undefined>();
  const [prospectName, setProspectName] = useState<string | undefined>();
  const [title, setTitle] = useState('');
  const [expectedAmount, setExpectedAmount] = useState('');
  const [expectedCloseDate, setExpectedCloseDate] = useState('');
  const [lines, setLines] = useState<LineDraft[]>([]);
  const [saving, setSaving] = useState(false);

  const fetchCustomerOptions = async (q: string): Promise<CustomerComboOption[]> => {
    const result = await getPortalCustomerOptions(q);
    const options: CustomerComboOption[] = result.items.map((item) => ({
      id: item.customer_id,
      label: `${item.customer_code} - ${item.customer_name}`,
      customerId: item.customer_id,
    }));
    if (result.blocked) {
      options.push({ id: BLOCKED_ID, label: result.blocked.message, disabled: true });
    } else if (result.prospect) {
      options.push({
        id: `${PROSPECT_PREFIX}${result.prospect.name}`,
        label: `Add "${result.prospect.name}" as a new prospect`,
        prospectName: result.prospect.name,
      });
    }
    return options;
  };

  const handleCustomerChange = (value: string, item?: CustomerComboOption) => {
    setCustomerValue(value);
    if (!item) return;
    if (item.customerId) {
      setCustomerId(item.customerId);
      setProspectName(undefined);
    } else if (item.prospectName) {
      setProspectName(item.prospectName);
      setCustomerId(undefined);
    }
  };

  const addLine = () =>
    setLines((prev) => [...prev, { key: nextLineKey(), productId: '', productLabel: '', qty: '1' }]);
  const removeLine = (key: string) => setLines((prev) => prev.filter((l) => l.key !== key));
  const updateLine = (key: string, patch: Partial<LineDraft>) =>
    setLines((prev) => prev.map((l) => (l.key === key ? { ...l, ...patch } : l)));

  const canSave = title.trim().length > 0 && !!expectedAmount && !!expectedCloseDate && !saving;

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!canSave) return;
    setSaving(true);
    try {
      const created = await createPortalSalesOpportunity({
        title: title.trim(),
        expected_amount: expectedAmount,
        expected_close_date: expectedCloseDate,
        ...(prospectName ? { prospect_name: prospectName } : { customer_id: customerId }),
        lines: lines
          .filter((l) => l.productId)
          .map((l) => ({ product_id: l.productId, qty: Number(l.qty) || 0 })),
      });
      toast.success('Opportunity logged');
      onCreated?.(created.id);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Failed to log the opportunity.');
    } finally {
      setSaving(false);
    }
  };

  return (
    <form onSubmit={submit} className="mx-auto flex w-full max-w-lg flex-col gap-4 px-3 py-4">
      <Card>
        <CardHeader>
          <CardTitle>Log a sales opportunity</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="customer-or-prospect">Customer or prospect</Label>
            <AsyncCombobox<CustomerComboOption>
              id="customer-or-prospect"
              value={customerValue}
              onChange={handleCustomerChange}
              fetchOptions={fetchCustomerOptions}
              optionValue={(o) => o.id}
              optionLabel={(o) => o.label}
              optionDisabled={(o) => !!o.disabled}
              placeholder="Search customer or prospect..."
              allowFreeText={false}
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
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="flex flex-row items-center justify-between">
          <CardTitle>Products</CardTitle>
          <Button type="button" variant="outline" size="sm" onClick={addLine}>
            <Plus className="size-4" />
            Add product
          </Button>
        </CardHeader>
        <CardContent className="flex flex-col gap-3">
          {lines.length === 0 ? (
            <p className="text-sm text-muted-foreground">No products yet</p>
          ) : (
            lines.map((line) => (
              <div key={line.key} className="flex items-end gap-2">
                <div className="flex-1 flex flex-col gap-1.5">
                  <Label htmlFor={`product-${line.key}`}>Product</Label>
                  <AsyncCombobox<PortalProductOption>
                    id={`product-${line.key}`}
                    value={line.productLabel}
                    onChange={(_v, item) =>
                      updateLine(line.key, {
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
                    onChange={(e) => updateLine(line.key, { qty: e.target.value })}
                  />
                </div>
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  aria-label="Remove product"
                  onClick={() => removeLine(line.key)}
                >
                  <Trash2 className="size-4" />
                  Remove
                </Button>
              </div>
            ))
          )}
        </CardContent>
      </Card>

      <Button type="submit" disabled={!canSave}>
        {saving ? <LoaderCircleIcon className="size-4 animate-spin" /> : null}
        Save
      </Button>
    </form>
  );
}
