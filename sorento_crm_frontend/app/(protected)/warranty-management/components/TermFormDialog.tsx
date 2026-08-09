'use client';

import { useEffect, useState } from 'react';
import { FormDialogScaffold } from '@/components/common/FormDialogScaffold';
import { SearchableMultiSelect } from '@/components/common/SearchableMultiSelect';
import { SearchableSelect } from '@/components/common/SearchableSelect';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';
import { Textarea } from '@/components/ui/textarea';
import { useDefectTypes } from '../hooks/useWarrantyConfig';
import type {
  WarrantyKindRef,
  WarrantyTermRow,
  WarrantyTermWrite,
} from '../types/warranty-config.types';

export function TermFormDialog({
  open,
  onOpenChange,
  initial,
  kinds,
  defaultKindId,
  onSubmit,
  isSubmitting,
  error,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  initial: WarrantyTermRow | null;
  kinds: WarrantyKindRef[];
  defaultKindId?: string;
  onSubmit: (body: WarrantyTermWrite) => Promise<void>;
  isSubmitting: boolean;
  error: string | null;
}) {
  const isEdit = !!initial;
  const { data: defectTypes } = useDefectTypes();

  const [kindId, setKindId] = useState('');
  const [partName, setPartName] = useState('');
  const [isLifetime, setIsLifetime] = useState(false);
  const [durationMonths, setDurationMonths] = useState('');
  const [bonusMonths, setBonusMonths] = useState('');
  const [installationIncluded, setInstallationIncluded] = useState(false);
  const [defectIds, setDefectIds] = useState<string[]>([]);
  const [qualifications, setQualifications] = useState('');
  const [exclusions, setExclusions] = useState('');

  useEffect(() => {
    if (!open) return;
    if (initial) {
      setKindId(initial.kind_id);
      setPartName(initial.part_name);
      setIsLifetime(initial.is_lifetime);
      setDurationMonths(initial.duration_months != null ? String(initial.duration_months) : '');
      setBonusMonths(
        initial.registration_bonus_months != null ? String(initial.registration_bonus_months) : '',
      );
      setInstallationIncluded(initial.installation_included);
      setDefectIds(initial.covered_defect_type_ids ?? []);
      setQualifications(initial.qualifications ?? '');
      setExclusions(initial.exclusions ?? '');
    } else {
      setKindId(defaultKindId ?? '');
      setPartName('');
      setIsLifetime(false);
      setDurationMonths('');
      setBonusMonths('');
      setInstallationIncluded(false);
      setDefectIds([]);
      setQualifications('');
      setExclusions('');
    }
  }, [open, initial, defaultKindId]);

  // AC-P3a: either a duration in months OR lifetime, never both and never neither.
  const durationValid = isLifetime
    ? true
    : durationMonths.trim().length > 0 && Number(durationMonths) > 0;
  const canSubmit = kindId.length > 0 && partName.trim().length > 0 && durationValid;

  return (
    <FormDialogScaffold
      open={open}
      onOpenChange={onOpenChange}
      title={isEdit ? 'Edit term' : 'Add term'}
      submitLabel={isEdit ? 'Save' : 'Create'}
      isPending={isSubmitting}
      error={error}
      onSubmit={async (e) => {
        e.preventDefault();
        if (!canSubmit) return;
        await onSubmit({
          kind_id: kindId,
          part_name: partName.trim(),
          duration_months: isLifetime ? null : Number(durationMonths),
          is_lifetime: isLifetime,
          covered_defect_type_ids: defectIds.length > 0 ? defectIds : null,
          installation_included: installationIncluded,
          registration_bonus_months: bonusMonths.trim() ? Number(bonusMonths) : null,
          qualifications: qualifications.trim() || null,
          exclusions: exclusions.trim() || null,
        });
      }}
    >
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <div className="space-y-1.5">
          <Label htmlFor="term-kind">Kind</Label>
          <SearchableSelect
            id="term-kind"
            value={kindId}
            onChange={setKindId}
            placeholder="Select a kind"
            options={kinds.map((k) => ({ value: k.id, label: k.name, searchText: k.code }))}
          />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="term-part">Part</Label>
          <Input
            id="term-part"
            value={partName}
            onChange={(e) => setPartName(e.target.value)}
            placeholder="Ceramic Body"
            autoComplete="off"
          />
        </div>

        <div className="flex items-center gap-2 sm:col-span-2">
          <Switch id="term-lifetime" checked={isLifetime} onCheckedChange={setIsLifetime} />
          <Label htmlFor="term-lifetime">Lifetime</Label>
        </div>

        <div className="space-y-1.5">
          <Label htmlFor="term-duration">Duration (months)</Label>
          <Input
            id="term-duration"
            type="number"
            min={1}
            value={durationMonths}
            disabled={isLifetime}
            onChange={(e) => setDurationMonths(e.target.value)}
          />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="term-bonus">Registration bonus (months)</Label>
          <Input
            id="term-bonus"
            type="number"
            min={0}
            value={bonusMonths}
            onChange={(e) => setBonusMonths(e.target.value)}
          />
        </div>

        <div className="space-y-1.5 sm:col-span-2">
          <Label>Covered defect types</Label>
          <SearchableMultiSelect
            value={defectIds}
            onChange={setDefectIds}
            placeholder="All defect types"
            options={(defectTypes ?? []).map((d) => ({ value: d.id, label: d.label }))}
          />
        </div>

        <div className="flex items-center gap-2 sm:col-span-2">
          <Switch
            id="term-installation"
            checked={installationIncluded}
            onCheckedChange={setInstallationIncluded}
          />
          <Label htmlFor="term-installation">Installation included</Label>
        </div>

        <div className="space-y-1.5 sm:col-span-2">
          <Label htmlFor="term-qualifications">Qualifications</Label>
          <Textarea
            id="term-qualifications"
            rows={3}
            value={qualifications}
            onChange={(e) => setQualifications(e.target.value)}
          />
        </div>
        <div className="space-y-1.5 sm:col-span-2">
          <Label htmlFor="term-exclusions">Exclusions</Label>
          <Textarea
            id="term-exclusions"
            rows={3}
            value={exclusions}
            onChange={(e) => setExclusions(e.target.value)}
          />
        </div>
      </div>
    </FormDialogScaffold>
  );
}
