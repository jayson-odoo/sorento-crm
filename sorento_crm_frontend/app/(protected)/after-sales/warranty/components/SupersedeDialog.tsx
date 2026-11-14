'use client';

import { useState } from 'react';
import { Button } from '@/components/ui/button';
import { DatePicker } from '@/components/ui/date-picker';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { ymd } from '../../service-jobs/lib/jobDates';
import { useSupersedePolicy } from '../hooks/useWarrantyConfig';
import { formatCivilDate, previousCivilDay } from '../lib/warrantyLabels';
import type { WarrantyPolicy } from '../types/warranty.types';

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** The incumbent. */
  policy: WarrantyPolicy;
}

export function SupersedeDialog({ open, onOpenChange, policy }: Props) {
  const supersede = useSupersedePolicy();
  const [version, setVersion] = useState('');
  const [start, setStart] = useState<Date | undefined>();

  const startIso = start ? ymd(start) : null;
  const valid = !!version.trim() && !!startIso && startIso > policy.effective_from;
  const closes = valid ? previousCivilDay(startIso) : null;

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!valid || !startIso) return;
    try {
      await supersede.mutateAsync({ id: policy.id, values: { version: version.trim(), effective_from: startIso } });
      onOpenChange(false);
    } catch {
      /* the mutation toasts the server's message */
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="overflow-hidden sm:max-w-md" aria-describedby={undefined}>
        <DialogHeader>
          <DialogTitle>Supersede {policy.version}</DialogTitle>
        </DialogHeader>
        <form onSubmit={submit} className="flex min-h-0 flex-1 flex-col gap-4">
          <DialogBody className="min-h-0 space-y-4 overflow-y-auto">
            <div className="space-y-1">
              <Label htmlFor="sp-version">New version</Label>
              <Input id="sp-version" aria-label="New version" value={version} onChange={(e) => setVersion(e.target.value)} />
            </div>
            <div className="space-y-1">
              <Label>Starts on</Label>
              <DatePicker value={start} onChange={setStart} ariaLabel="Starts on" portal />
            </div>
            {valid && closes && (
              <p className="text-sm">
                {`${policy.version} closes ${formatCivilDate(closes)}; ${version.trim()} runs from ${formatCivilDate(startIso)}`}
              </p>
            )}
          </DialogBody>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
            <Button type="submit" disabled={!valid || supersede.isPending}>Supersede</Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
