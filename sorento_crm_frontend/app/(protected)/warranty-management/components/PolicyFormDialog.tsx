'use client';

import { useEffect, useState } from 'react';
import { FormDialogScaffold } from '@/components/common/FormDialogScaffold';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import type { WarrantyPolicyRow, WarrantyPolicyWrite } from '../types/warranty-config.types';

export type PolicyDialogMode = 'create' | 'edit' | 'supersede';

const TITLES: Record<PolicyDialogMode, string> = {
  create: 'Add policy',
  edit: 'Edit policy',
  supersede: 'Supersede policy',
};

const SUBMIT: Record<PolicyDialogMode, string> = {
  create: 'Create',
  edit: 'Save',
  supersede: 'Publish',
};

/**
 * One modal for all three writes. Supersede differs only in what the server does
 * with the payload (close the incumbent, create the successor, one transaction -
 * AC-P2a), so a second form would be the same fields with a different button and
 * a second place for the date rules to drift.
 */
export function PolicyFormDialog({
  open,
  onOpenChange,
  mode,
  initial,
  incumbent,
  onSubmit,
  isSubmitting,
  error,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  mode: PolicyDialogMode;
  /** The row being edited (`edit` only). */
  initial?: WarrantyPolicyRow | null;
  /** The policy being superseded (`supersede` only) - drives the earliest start. */
  incumbent?: WarrantyPolicyRow | null;
  onSubmit: (body: WarrantyPolicyWrite) => Promise<void>;
  isSubmitting: boolean;
  error: string | null;
}) {
  const [version, setVersion] = useState('');
  const [effectiveFrom, setEffectiveFrom] = useState('');
  const [effectiveTo, setEffectiveTo] = useState('');
  const [policyText, setPolicyText] = useState('');

  useEffect(() => {
    if (!open) return;
    if (mode === 'edit' && initial) {
      setVersion(initial.version);
      setEffectiveFrom(initial.effective_from);
      setEffectiveTo(initial.effective_to ?? '');
      setPolicyText(initial.policy_text ?? '');
    } else {
      setVersion('');
      setEffectiveFrom('');
      setEffectiveTo('');
      setPolicyText('');
    }
  }, [open, mode, initial]);

  const canSubmit = version.trim().length > 0 && effectiveFrom.length > 0;

  return (
    <FormDialogScaffold
      open={open}
      onOpenChange={onOpenChange}
      title={TITLES[mode]}
      submitLabel={SUBMIT[mode]}
      isPending={isSubmitting}
      error={error}
      onSubmit={async (e) => {
        e.preventDefault();
        if (!canSubmit) return;
        await onSubmit({
          version: version.trim(),
          effective_from: effectiveFrom,
          effective_to: effectiveTo || null,
          policy_text: policyText.trim() || null,
        });
      }}
    >
      {mode === 'supersede' && incumbent ? (
        <div className="rounded-md border border-border bg-muted/40 px-3 py-2 text-sm">
          <span className="text-muted-foreground">Replacing</span>{' '}
          <span className="font-medium">{incumbent.version}</span>
        </div>
      ) : null}

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <div className="space-y-1.5">
          <Label htmlFor="policy-version">Version</Label>
          <Input
            id="policy-version"
            value={version}
            onChange={(e) => setVersion(e.target.value)}
            placeholder="v16"
            autoComplete="off"
          />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="policy-from">Effective from</Label>
          <Input
            id="policy-from"
            type="date"
            value={effectiveFrom}
            min={mode === 'supersede' && incumbent ? incumbent.effective_from : undefined}
            onChange={(e) => setEffectiveFrom(e.target.value)}
          />
        </div>
        <div className="space-y-1.5 sm:col-span-2">
          <Label htmlFor="policy-to">Effective to</Label>
          <Input
            id="policy-to"
            type="date"
            value={effectiveTo}
            min={effectiveFrom || undefined}
            onChange={(e) => setEffectiveTo(e.target.value)}
            placeholder="Leave blank for open ended"
          />
        </div>
        <div className="space-y-1.5 sm:col-span-2">
          <Label htmlFor="policy-text">Policy text</Label>
          <Textarea
            id="policy-text"
            value={policyText}
            onChange={(e) => setPolicyText(e.target.value)}
            rows={6}
          />
        </div>
      </div>
    </FormDialogScaffold>
  );
}
