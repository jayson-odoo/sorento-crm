'use client';

import { useState } from 'react';
import { LoaderCircleIcon, Plus } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { toast } from '@/lib/toast';
import { AsyncCombobox } from '../../components/AsyncCombobox';
import { createPortalSalesOpportunity } from '../../lib/sales-opportunity-service';
import {
  type CustomerComboOption,
  fetchCustomerOrProspectOptions,
} from '../lib/customerOrProspect';
import { PortalOpportunityLineRow, nextLineKey, type LineDraft } from './PortalOpportunityLineRow';

/**
 * The portal Sales Opportunity CREATE form (UAC S2-10, S2-15, S2-16; plan 3.5, N10, N11).
 *
 * The same "Customer or prospect" search and Products table contract as the CRM modal, over
 * the portal's own service and `AsyncCombobox` (the complaint form's product-line pattern).
 * No agent field anywhere - the agent comes from the token, never the form.
 *
 * Edit lives on `SalesOpportunityPortalDetail` itself, in place (Phase 3 fix2 should-fix 5) -
 * this component is create-only; an earlier round routed Edit through a second instance of it
 * with `initial`/`onSaved` props, which swapped the whole read view for the create form
 * instead of turning its own fields into inputs. Reverted.
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

  const handleCustomerChange = (value: string, item?: CustomerComboOption) => {
    setCustomerValue(value);
    if (item) {
      if (item.customerId) {
        setCustomerId(item.customerId);
        setProspectName(undefined);
      } else if (item.prospectName) {
        setProspectName(item.prospectName);
        setCustomerId(undefined);
      }
      return;
    }
    // Reviewer should-fix 6: a keystroke with no item means the typed text no longer
    // matches whatever was picked before - clear the stale selection, or a customer
    // chosen earlier and since edited away from would still be the one submitted.
    setCustomerId(undefined);
    setProspectName(undefined);
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
    const payload = {
      title: title.trim(),
      expected_amount: expectedAmount,
      expected_close_date: expectedCloseDate,
      ...(prospectName ? { prospect_name: prospectName } : { customer_id: customerId }),
      lines: lines
        .filter((l) => l.productId)
        .map((l) => ({ product_id: l.productId, qty: Number(l.qty) || 0 })),
    };
    try {
      const created = await createPortalSalesOpportunity(payload);
      toast.success('Opportunity logged');
      onCreated?.(created.id);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Failed to save the opportunity.');
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
              fetchOptions={fetchCustomerOrProspectOptions}
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
              <PortalOpportunityLineRow
                key={line.key}
                line={line}
                onChange={(patch) => updateLine(line.key, patch)}
                onRemove={() => removeLine(line.key)}
              />
            ))
          )}
        </CardContent>
      </Card>

      <div className="flex items-center gap-2">
        <Button type="submit" disabled={!canSave}>
          {saving ? <LoaderCircleIcon className="size-4 animate-spin" /> : null}
          Save
        </Button>
      </div>
    </form>
  );
}
