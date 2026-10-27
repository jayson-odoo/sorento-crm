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
import { SearchableSelect } from '@/components/common/SearchableSelect';
import { useSaveSalesAgentClass } from '../../hooks/useSalesAgents';
import type { SalesAgentClassPayload, SalesAgentClassRow } from '../../types/salesAgent.types';

export const CLASS_OPTIONS = [
  { value: 'retail', label: 'Dealer' },
  { value: 'project', label: 'Project team' },
  { value: 'other', label: 'Other' },
];

/** The body the modal sends: an empty month is an open end (null). */
export function buildClassPayload(input: {
  demandClass: string;
  fromMonth: string;
  toMonth: string;
}): SalesAgentClassPayload {
  return {
    demand_class: input.demandClass,
    from_month: input.fromMonth || null,
    to_month: input.toMonth || null,
  };
}

export default function SalesAgentClassModal({
  agentId,
  open,
  onOpenChange,
  row,
}: {
  agentId: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  row: SalesAgentClassRow | null;
}) {
  const save = useSaveSalesAgentClass(agentId);
  const [demandClass, setDemandClass] = useState('');
  const [fromMonth, setFromMonth] = useState('');
  const [toMonth, setToMonth] = useState('');

  useEffect(() => {
    if (!open) return;
    setDemandClass(row?.demand_class ?? '');
    setFromMonth(row?.from_month ?? '');
    setToMonth(row?.to_month ?? '');
  }, [open, row]);

  const inverted = !!fromMonth && !!toMonth && toMonth < fromMonth;
  const canSave = !!demandClass && !inverted && !save.isPending;

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!canSave) return;
    try {
      await save.mutateAsync({
        rowId: row?.id ?? null,
        payload: buildClassPayload({ demandClass, fromMonth, toMonth }),
      });
      onOpenChange(false);
    } catch {
      // The hook toasted the reason; the modal stays open.
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{row ? 'Edit class' : 'Add class'}</DialogTitle>
        </DialogHeader>
        <form onSubmit={submit} className="flex flex-col gap-4">
          <DialogBody className="flex flex-col gap-4">
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="sa-class-class">Class</Label>
              <SearchableSelect
                id="sa-class-class"
                value={demandClass}
                onChange={setDemandClass}
                options={CLASS_OPTIONS}
                placeholder="Pick a class"
              />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="sa-class-from">From month</Label>
              <div className="flex items-center gap-2">
                <Input
                  id="sa-class-from"
                  type="month"
                  value={fromMonth}
                  onChange={(e) => setFromMonth(e.target.value)}
                  className="w-44"
                />
                {fromMonth ? (
                  <Button type="button" variant="ghost" size="sm" onClick={() => setFromMonth('')}>
                    Clear
                  </Button>
                ) : null}
              </div>
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="sa-class-to">To month</Label>
              <div className="flex items-center gap-2">
                <Input
                  id="sa-class-to"
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
              {inverted ? <p className="text-xs text-destructive">To month is before From month.</p> : null}
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
