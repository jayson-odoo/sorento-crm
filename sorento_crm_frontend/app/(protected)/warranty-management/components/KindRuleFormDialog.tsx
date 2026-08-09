'use client';

import { useEffect, useState } from 'react';
import { FormDialogScaffold } from '@/components/common/FormDialogScaffold';
import { SearchableSelect } from '@/components/common/SearchableSelect';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import {
  KIND_RULE_MATCH_TYPES,
  KIND_RULE_MATCH_TYPE_LABEL,
  type KindRuleMatchType,
  type WarrantyKindRef,
  type WarrantyKindRuleRow,
  type WarrantyKindRuleWrite,
} from '../types/warranty-config.types';

const VALUE_PLACEHOLDER: Record<KindRuleMatchType, string> = {
  category: 'SANITARY',
  model_prefix: 'SRTWC',
  model_list: 'SRTMCB8071-BL, SRTMCB6071-BL',
  series: 'Honeycomb',
};

export function KindRuleFormDialog({
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
  initial: WarrantyKindRuleRow | null;
  kinds: WarrantyKindRef[];
  defaultKindId: string;
  onSubmit: (body: WarrantyKindRuleWrite) => Promise<void>;
  isSubmitting: boolean;
  error: string | null;
}) {
  const isEdit = !!initial;
  const [kindId, setKindId] = useState('');
  const [matchType, setMatchType] = useState<KindRuleMatchType>('model_prefix');
  const [matchValue, setMatchValue] = useState('');
  const [priority, setPriority] = useState('0');

  useEffect(() => {
    if (!open) return;
    if (initial) {
      setKindId(initial.kind_id);
      setMatchType(initial.match_type);
      setMatchValue(initial.match_value);
      setPriority(String(initial.priority));
    } else {
      setKindId(defaultKindId);
      setMatchType('model_prefix');
      setMatchValue('');
      setPriority('0');
    }
  }, [open, initial, defaultKindId]);

  const canSubmit = kindId.length > 0 && matchValue.trim().length > 0;

  return (
    <FormDialogScaffold
      open={open}
      onOpenChange={onOpenChange}
      title={isEdit ? 'Edit rule' : 'Add rule'}
      submitLabel={isEdit ? 'Save' : 'Create'}
      isPending={isSubmitting}
      error={error}
      onSubmit={async (e) => {
        e.preventDefault();
        if (!canSubmit) return;
        await onSubmit({
          kind_id: kindId,
          match_type: matchType,
          match_value: matchValue.trim(),
          priority: Number(priority) || 0,
        });
      }}
    >
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <div className="space-y-1.5 sm:col-span-2">
          <Label htmlFor="rule-kind">Kind</Label>
          <SearchableSelect
            id="rule-kind"
            value={kindId}
            onChange={setKindId}
            placeholder="Select a kind"
            options={kinds.map((k) => ({ value: k.id, label: k.name, searchText: k.code }))}
          />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="rule-match-type">Match type</Label>
          <SearchableSelect
            id="rule-match-type"
            value={matchType}
            onChange={(v) => setMatchType(v as KindRuleMatchType)}
            options={KIND_RULE_MATCH_TYPES.map((t) => ({
              value: t,
              label: KIND_RULE_MATCH_TYPE_LABEL[t],
            }))}
          />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="rule-priority">Priority</Label>
          <Input
            id="rule-priority"
            type="number"
            value={priority}
            onChange={(e) => setPriority(e.target.value)}
          />
        </div>
        <div className="space-y-1.5 sm:col-span-2">
          <Label htmlFor="rule-value">Value</Label>
          {matchType === 'model_list' ? (
            <Textarea
              id="rule-value"
              value={matchValue}
              onChange={(e) => setMatchValue(e.target.value)}
              placeholder={VALUE_PLACEHOLDER[matchType]}
              rows={3}
            />
          ) : (
            <Input
              id="rule-value"
              value={matchValue}
              onChange={(e) => setMatchValue(e.target.value)}
              placeholder={VALUE_PLACEHOLDER[matchType]}
              autoComplete="off"
            />
          )}
        </div>
      </div>
    </FormDialogScaffold>
  );
}
