'use client';

import { useEffect, useState } from 'react';
import { FormDialogScaffold } from '@/components/common/FormDialogScaffold';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';
import type { WarrantyKindRow, WarrantyKindWrite } from '../types/warranty-config.types';

export function KindFormDialog({
  open,
  onOpenChange,
  initial,
  nextSortOrder,
  onSubmit,
  isSubmitting,
  error,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  initial: WarrantyKindRow | null;
  nextSortOrder: number;
  onSubmit: (body: WarrantyKindWrite) => Promise<void>;
  isSubmitting: boolean;
  error: string | null;
}) {
  const isEdit = !!initial;
  const [code, setCode] = useState('');
  const [name, setName] = useState('');
  const [consumerLabel, setConsumerLabel] = useState('');
  const [sortOrder, setSortOrder] = useState('0');
  const [isActive, setIsActive] = useState(true);

  useEffect(() => {
    if (!open) return;
    if (initial) {
      setCode(initial.code);
      setName(initial.name);
      setConsumerLabel(initial.consumer_label ?? '');
      setSortOrder(String(initial.sort_order));
      setIsActive(initial.is_active);
    } else {
      setCode('');
      setName('');
      setConsumerLabel('');
      setSortOrder(String(nextSortOrder));
      setIsActive(true);
    }
  }, [open, initial, nextSortOrder]);

  const canSubmit = code.trim().length > 0 && name.trim().length > 0;

  return (
    <FormDialogScaffold
      open={open}
      onOpenChange={onOpenChange}
      title={isEdit ? 'Edit kind' : 'Add kind'}
      submitLabel={isEdit ? 'Save' : 'Create'}
      isPending={isSubmitting}
      error={error}
      onSubmit={async (e) => {
        e.preventDefault();
        if (!canSubmit) return;
        await onSubmit({
          code: code.trim(),
          name: name.trim(),
          consumer_label: consumerLabel.trim() || null,
          consumer_icon: initial?.consumer_icon ?? null,
          sort_order: Number(sortOrder) || 0,
          is_active: isActive,
        });
      }}
    >
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <div className="space-y-1.5">
          <Label htmlFor="kind-code">Code</Label>
          <Input
            id="kind-code"
            value={code}
            onChange={(e) => setCode(e.target.value)}
            placeholder="water_closet"
            autoComplete="off"
          />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="kind-sort">Sort order</Label>
          <Input
            id="kind-sort"
            type="number"
            value={sortOrder}
            onChange={(e) => setSortOrder(e.target.value)}
          />
        </div>
        <div className="space-y-1.5 sm:col-span-2">
          <Label htmlFor="kind-name">Name</Label>
          <Input id="kind-name" value={name} onChange={(e) => setName(e.target.value)} />
        </div>
        <div className="space-y-1.5 sm:col-span-2">
          <Label htmlFor="kind-consumer-label">Consumer label</Label>
          <Input
            id="kind-consumer-label"
            value={consumerLabel}
            onChange={(e) => setConsumerLabel(e.target.value)}
          />
        </div>
        <div className="flex items-center gap-2 sm:col-span-2">
          <Switch id="kind-active" checked={isActive} onCheckedChange={setIsActive} />
          <Label htmlFor="kind-active">Active</Label>
        </div>
      </div>
    </FormDialogScaffold>
  );
}
