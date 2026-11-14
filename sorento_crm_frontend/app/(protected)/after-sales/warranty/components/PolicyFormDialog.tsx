'use client';

import { useEffect, useState } from 'react';
import { Button } from '@/components/ui/button';
import { DatePicker } from '@/components/ui/date-picker';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { ymd } from '../../service-jobs/lib/jobDates';
import { useCreatePolicy, useUpdatePolicy } from '../hooks/useWarrantyConfig';
import type { WarrantyPolicy } from '../types/warranty.types';

export function parseCivil(value: string | null | undefined): Date | undefined {
  const [y, m, d] = (value ?? '').split('-').map(Number);
  return y && m && d ? new Date(y, m - 1, d) : undefined;
}

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Present = Edit. */
  policy?: WarrantyPolicy | null;
}

export function PolicyFormDialog({ open, onOpenChange, policy }: Props) {
  const create = useCreatePolicy();
  const update = useUpdatePolicy();
  const [version, setVersion] = useState('');
  const [from, setFrom] = useState<Date | undefined>();
  const [to, setTo] = useState<Date | undefined>();
  const [text, setText] = useState('');
  const [tried, setTried] = useState(false);
  const [filledFor, setFilledFor] = useState<string | null>(null);

  useEffect(() => {
    const key = open ? (policy?.id ?? 'new') : null;
    if (key === filledFor) return;
    setFilledFor(key);
    if (!key) return;
    setVersion(policy?.version ?? '');
    setFrom(parseCivil(policy?.effective_from));
    setTo(parseCivil(policy?.effective_to));
    setText(policy?.policy_text ?? '');
    setTried(false);
  }, [open, policy, filledFor]);

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    setTried(true);
    if (!version.trim() || !from) return;
    const values = {
      version: version.trim(),
      effective_from: ymd(from),
      effective_to: to ? ymd(to) : null,
      policy_text: text.trim() || null,
    };
    try {
      if (policy) await update.mutateAsync({ id: policy.id, values });
      else await create.mutateAsync(values);
      onOpenChange(false);
    } catch {
      /* the mutation toasts the server's message */
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="overflow-hidden sm:max-w-lg" aria-describedby={undefined}>
        <DialogHeader>
          <DialogTitle>{policy ? 'Edit policy' : 'Create policy'}</DialogTitle>
        </DialogHeader>
        <form onSubmit={submit} className="flex min-h-0 flex-1 flex-col gap-4">
          <DialogBody className="min-h-0 space-y-4 overflow-y-auto">
            <div className="space-y-1">
              <Label htmlFor="wp-version">Version *</Label>
              <Input id="wp-version" value={version} onChange={(e) => setVersion(e.target.value)} />
              {tried && !version.trim() && (
                <p role="alert" className="text-sm text-destructive">Version is required.</p>
              )}
            </div>
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              <div className="space-y-1">
                <Label>In force from *</Label>
                <DatePicker value={from} onChange={setFrom} ariaLabel="In force from" portal required />
                {tried && !from && (
                  <p role="alert" className="text-sm text-destructive">In force from is required.</p>
                )}
              </div>
              <div className="space-y-1">
                <Label>In force to</Label>
                <DatePicker value={to} onChange={setTo} ariaLabel="In force to" portal />
              </div>
            </div>
            <div className="space-y-1">
              <Label htmlFor="wp-text">Policy text</Label>
              <Textarea id="wp-text" rows={6} value={text} onChange={(e) => setText(e.target.value)} />
            </div>
          </DialogBody>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
            <Button type="submit" disabled={create.isPending || update.isPending}>
              {policy ? 'Save' : 'Create'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
