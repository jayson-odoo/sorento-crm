'use client';

import { useEffect, useState } from 'react';
import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
import { Input } from '@/components/ui/input';
import { NumberInput } from '@/components/ui/number-input';
import { Label } from '@/components/ui/label';
import { SearchableMultiSelect } from '@/components/common/SearchableMultiSelect';
import { SearchableSelect } from '@/components/common/SearchableSelect';
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { useCreateTerm, useDefectOptions, useKindOptions, useUpdateTerm } from '../hooks/useWarrantyConfig';
import type { WarrantyTerm } from '../types/warranty.types';

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  policyId: string;
  /** Present = Edit. */
  term?: WarrantyTerm | null;
}

const NEITHER = 'Enter the months or tick Lifetime';
const BOTH = 'Lifetime has no months: clear one of them';

export function TermFormDialog({ open, onOpenChange, policyId, term }: Props) {
  const create = useCreateTerm();
  const update = useUpdateTerm();
  const { data: kinds = [] } = useKindOptions();
  const { data: defects = [] } = useDefectOptions();
  const [kindId, setKindId] = useState('');
  const [part, setPart] = useState('');
  const [lifetime, setLifetime] = useState(false);
  const [months, setMonths] = useState('');
  const [defectIds, setDefectIds] = useState<string[]>([]);
  const [installation, setInstallation] = useState(false);
  const [tried, setTried] = useState(false);
  const [filledFor, setFilledFor] = useState<string | null>(null);

  useEffect(() => {
    const key = open ? (term?.id ?? 'new') : null;
    if (key === filledFor) return;
    setFilledFor(key);
    if (!key) return;
    setKindId(term?.kind_id ?? '');
    setPart(term?.part_name ?? '');
    setLifetime(term?.is_lifetime ?? false);
    setMonths(term?.duration_months ? String(term.duration_months) : '');
    setDefectIds(term?.covered_defect_type_ids ?? []);
    setInstallation(term?.installation_included ?? false);
    setTried(false);
  }, [open, term, filledFor]);

  const monthsValue = Number.parseInt(months, 10);
  const hasMonths = Number.isFinite(monthsValue) && monthsValue > 0;
  const coverError = lifetime && hasMonths ? BOTH : !lifetime && !hasMonths ? NEITHER : null;

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    setTried(true);
    if ((!term && !kindId) || !part.trim() || coverError) return;
    const values = {
      part_name: part.trim(),
      duration_months: lifetime ? null : monthsValue,
      is_lifetime: lifetime,
      covered_defect_type_ids: defectIds.length ? defectIds : null,
      installation_included: installation,
    };
    try {
      if (term) await update.mutateAsync({ id: term.id, values });
      else await create.mutateAsync({ policy_id: policyId, kind_id: kindId, ...values });
      onOpenChange(false);
    } catch {
      /* the mutation toasts the server's message */
    }
  };

  const error = (text: string | null, show: boolean) =>
    show && text ? <p role="alert" className="text-sm text-destructive">{text}</p> : null;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="overflow-hidden sm:max-w-lg" aria-describedby={undefined}>
        <DialogHeader>
          <DialogTitle>{term ? 'Edit term' : 'Create term'}</DialogTitle>
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
                disabled={!!term}
              />
              {error('Kind is required.', tried && !term && !kindId)}
            </div>
            <div className="space-y-1">
              <Label htmlFor="wt-part">Part *</Label>
              <Input id="wt-part" aria-label="Part" value={part} onChange={(e) => setPart(e.target.value)} />
              {error('Part is required.', tried && !part.trim())}
            </div>
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              <div className="space-y-1">
                <Label htmlFor="wt-months">Months</Label>
                <NumberInput
                  id="wt-months"
                  min={0}
                  value={months}
                  onChange={(e) => setMonths(e.target.value)}
                />
              </div>
              <div className="flex items-end gap-2 pb-2">
                <Checkbox id="wt-lifetime" checked={lifetime} onCheckedChange={(v) => setLifetime(v === true)} />
                <Label htmlFor="wt-lifetime">Lifetime</Label>
              </div>
            </div>
            {error(coverError, tried)}
            <div className="space-y-1">
              <Label>Defects</Label>
              <SearchableMultiSelect
                value={defectIds}
                onChange={setDefectIds}
                options={defects.map((d) => ({ value: d.id, label: d.label }))}
                placeholder="All defects"
                aria-label="Defects"
                clearable
              />
            </div>
            <div className="flex items-center gap-2">
              <Checkbox
                id="wt-installation"
                checked={installation}
                onCheckedChange={(v) => setInstallation(v === true)}
              />
              <Label htmlFor="wt-installation">Installation included</Label>
            </div>
          </DialogBody>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
            <Button type="submit" disabled={create.isPending || update.isPending}>{term ? 'Save' : 'Create'}</Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
