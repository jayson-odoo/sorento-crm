'use client';

import { useState, type FormEvent } from 'react';
import { LoaderCircleIcon } from 'lucide-react';
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
import { Label } from '@/components/ui/label';
import { NumberInput } from '@/components/ui/number-input';
import { Switch } from '@/components/ui/switch';
import { SearchableSelect } from '@/components/common/SearchableSelect';
import { useSaveParty } from '../hooks/useCosting';
import type { CostingParty, PartyBody } from '../types/costing.types';

const METHOD_OPTIONS = [
  { value: 'primary', label: 'Primary supplier' },
  { value: 'average', label: 'Average of supplier prices' },
  { value: 'last_po', label: 'Last PO price' },
];

function Form({ party, onDone }: { party: CostingParty; onDone: () => void }) {
  const save = useSaveParty();
  const [markup, setMarkup] = useState(party.markup_pct === null ? '' : String(party.markup_pct));
  const [method, setMethod] = useState(party.cost_method ?? '');
  const [active, setActive] = useState(party.is_active ?? true);
  const [problem, setProblem] = useState<string | null>(null);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    const value = Number(markup);
    if (markup.trim() === '' || !Number.isFinite(value) || value < 0) {
      setProblem('Enter a mark-up of 0 or more.');
      return;
    }
    setProblem(null);
    try {
      await save.mutateAsync({
        customerId: party.customer_id,
        body: {
          markup_pct: value,
          cost_method: (method || null) as PartyBody['cost_method'],
          is_active: active,
        },
      });
      onDone();
    } catch {
      // The hook toasted the reason; the dialog stays open.
    }
  };

  return (
    <form onSubmit={(e) => void submit(e)}>
      <DialogBody className="space-y-4">
        <div className="flex flex-col gap-1">
          <Label htmlFor="costing-party-markup">Party mark-up (%)</Label>
          <NumberInput
            id="costing-party-markup"
            step="any"
            min={0}
            value={markup}
            onChange={(e) => setMarkup(e.target.value)}
          />
        </div>
        <div className="flex flex-col gap-1">
          <Label htmlFor="costing-party-method">Cost method</Label>
          <SearchableSelect
            id="costing-party-method"
            aria-label="Cost method"
            value={method}
            onChange={setMethod}
            options={METHOD_OPTIONS}
            placeholder="Company default"
            clearable
          />
        </div>
        <label className="flex items-center gap-2 text-sm">
          <Switch checked={active} onCheckedChange={setActive} aria-label="Active" />
          Active
        </label>
        {problem ? (
          <p role="alert" className="text-sm text-destructive">
            {problem}
          </p>
        ) : null}
      </DialogBody>
      <DialogFooter>
        <Button type="button" variant="outline" onClick={onDone}>
          Cancel
        </Button>
        <Button type="submit" disabled={save.isPending}>
          {save.isPending ? <LoaderCircleIcon className="me-2 size-4 animate-spin" /> : null}
          Save
        </Button>
      </DialogFooter>
    </form>
  );
}

/** A party's default mark-up, cost method and active flag; the first save creates its profile. */
export function PartyProfileDialog({
  open,
  onOpenChange,
  party,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  party: CostingParty;
}) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md" aria-describedby={undefined}>
        <DialogHeader>
          <DialogTitle className="pe-8 break-words">{party.customer_name}</DialogTitle>
          <DialogDescription className="sr-only">Party mark-up and cost method.</DialogDescription>
        </DialogHeader>
        {open ? <Form party={party} onDone={() => onOpenChange(false)} /> : null}
      </DialogContent>
    </Dialog>
  );
}

export default PartyProfileDialog;
