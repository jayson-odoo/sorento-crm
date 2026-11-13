'use client';

import { useEffect, useState } from 'react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { SearchableSelect } from '@/components/common/SearchableSelect';
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { useCreateRule, useKindOptions, useUpdateRule } from '../hooks/useWarrantyConfig';
import { MATCH_TYPES, formatMatchTypeLabel } from '../lib/warrantyLabels';
import type { MatchType, WarrantyRule } from '../types/warranty.types';

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Present = Edit. */
  rule?: WarrantyRule | null;
}

export function RuleFormDialog({ open, onOpenChange, rule }: Props) {
  const create = useCreateRule();
  const update = useUpdateRule();
  const { data: kinds = [] } = useKindOptions();
  const [kindId, setKindId] = useState('');
  const [matchType, setMatchType] = useState<MatchType | ''>('');
  const [value, setValue] = useState('');
  const [priority, setPriority] = useState('0');
  const [tried, setTried] = useState(false);
  const [filledFor, setFilledFor] = useState<string | null>(null);

  useEffect(() => {
    const key = open ? (rule?.id ?? 'new') : null;
    if (key === filledFor) return;
    setFilledFor(key);
    if (!key) return;
    setKindId(rule?.kind_id ?? '');
    setMatchType(rule?.match_type ?? '');
    setValue(rule?.match_value ?? '');
    setPriority(String(rule?.priority ?? 0));
    setTried(false);
  }, [open, rule, filledFor]);

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    setTried(true);
    if (!kindId || !matchType || !value.trim()) return;
    const values = {
      kind_id: kindId,
      match_type: matchType,
      match_value: value.trim(),
      priority: Number.parseInt(priority, 10) || 0,
    };
    try {
      if (rule) await update.mutateAsync({ id: rule.id, values });
      else await create.mutateAsync(values);
      onOpenChange(false);
    } catch {
      /* the mutation toasts the server's message */
    }
  };

  const missing = (ok: boolean, label: string) =>
    tried && !ok ? <p role="alert" className="text-sm text-destructive">{label} is required.</p> : null;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="overflow-hidden sm:max-w-md">
        <DialogHeader>
          <DialogTitle>{rule ? 'Edit rule' : 'Create rule'}</DialogTitle>
          <DialogDescription className="sr-only">Kind rule.</DialogDescription>
        </DialogHeader>
        <form onSubmit={submit} className="flex min-h-0 flex-1 flex-col gap-4">
          <DialogBody className="min-h-0 space-y-4 overflow-y-auto">
            <div className="space-y-1">
              <Label>Kind *</Label>
              <SearchableSelect
                value={kindId}
                onChange={setKindId}
                options={kinds.map((k) => ({ value: k.id, label: k.name }))}
                placeholder="Select kind"
                aria-label="Kind"
              />
              {missing(!!kindId, 'Kind')}
            </div>
            <div className="space-y-1">
              <Label>Match *</Label>
              <SearchableSelect
                value={matchType}
                onChange={(v) => setMatchType(v as MatchType | '')}
                options={MATCH_TYPES.map((t) => ({ value: t, label: formatMatchTypeLabel(t) }))}
                placeholder="Select match"
                aria-label="Match"
              />
              {missing(!!matchType, 'Match')}
            </div>
            <div className="space-y-1">
              <Label htmlFor="wr-value">Value *</Label>
              <Input id="wr-value" value={value} onChange={(e) => setValue(e.target.value)} />
              {missing(!!value.trim(), 'Value')}
            </div>
            <div className="space-y-1">
              <Label htmlFor="wr-priority">Priority</Label>
              <Input id="wr-priority" type="number" value={priority} onChange={(e) => setPriority(e.target.value)} />
            </div>
          </DialogBody>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
            <Button type="submit" disabled={create.isPending || update.isPending}>{rule ? 'Save' : 'Create'}</Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
