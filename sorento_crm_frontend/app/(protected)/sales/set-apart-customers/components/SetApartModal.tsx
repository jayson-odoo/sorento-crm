'use client';

import { useEffect, useState } from 'react';
import { LoaderCircleIcon } from 'lucide-react';
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
import { useSaveSetApart } from '../hooks/useSetApart';
import { getSetApartCustomerOptions } from '../services/setApartService';
import type { SetApartRow, SetApartSavePayload } from '../types/setApart.types';

/** The body the modal sends: To month empty means still set apart (null). */
export function buildSetApartPayload(input: {
  customerId: string;
  fromMonth: string;
  toMonth: string;
}): SetApartSavePayload {
  return {
    customer_id: input.customerId,
    from_month: input.fromMonth,
    to_month: input.toMonth || null,
  };
}

const fetchCustomers = async (query: string): Promise<SearchableSelectOption[]> =>
  getSetApartCustomerOptions(query);

/** Add / Edit a set-apart customer. `row` null = add. */
export default function SetApartModal({
  open,
  onOpenChange,
  row,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  row: SetApartRow | null;
}) {
  const save = useSaveSetApart();
  const [customerId, setCustomerId] = useState('');
  const [customerOption, setCustomerOption] = useState<SearchableSelectOption | undefined>();
  const [fromMonth, setFromMonth] = useState('');
  const [toMonth, setToMonth] = useState('');

  useEffect(() => {
    if (!open) return;
    setCustomerId(row?.customer_id ?? '');
    setCustomerOption(
      row
        ? {
            value: row.customer_id,
            label: [row.debtor_code, row.customer_name].filter(Boolean).join(' - '),
          }
        : undefined,
    );
    setFromMonth(row?.from_month ?? '');
    setToMonth(row?.to_month ?? '');
  }, [open, row]);

  const inverted = !!fromMonth && !!toMonth && toMonth < fromMonth;
  const canSave = !!customerId && !!fromMonth && !inverted && !save.isPending;

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!canSave) return;
    try {
      await save.mutateAsync({
        id: row?.id ?? null,
        payload: buildSetApartPayload({ customerId, fromMonth, toMonth }),
      });
      onOpenChange(false);
    } catch {
      // The hook toasted the reason; the modal stays open with what was typed.
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{row ? 'Edit set-apart customer' : 'Add set-apart customer'}</DialogTitle>
        </DialogHeader>
        <form onSubmit={submit} className="flex flex-col gap-4">
          <DialogBody className="flex flex-col gap-4">
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="set-apart-customer">Customer</Label>
              <SearchableSelect
                id="set-apart-customer"
                value={customerId}
                onChange={setCustomerId}
                onOptionChange={(opt) => setCustomerOption(opt ?? undefined)}
                fetchOptions={fetchCustomers}
                selectedOption={customerOption}
                placeholder="Search customers"
                emptyMessage="No customers found."
                wrapOptions
              />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="set-apart-from">From month</Label>
              <Input
                id="set-apart-from"
                type="month"
                required
                value={fromMonth}
                onChange={(e) => setFromMonth(e.target.value)}
                className="w-44"
              />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="set-apart-to">To month</Label>
              <div className="flex items-center gap-2">
                <Input
                  id="set-apart-to"
                  type="month"
                  min={fromMonth || undefined}
                  value={toMonth}
                  onChange={(e) => setToMonth(e.target.value)}
                  className="w-44"
                />
                {toMonth ? (
                  <Button type="button" variant="ghost" size="sm" onClick={() => setToMonth('')}>
                    Clear
                  </Button>
                ) : null}
              </div>
              {inverted ? (
                <p className="text-xs text-destructive">To month is before From month.</p>
              ) : null}
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
