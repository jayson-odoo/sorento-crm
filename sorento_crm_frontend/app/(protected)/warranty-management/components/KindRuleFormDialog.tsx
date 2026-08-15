'use client';

import { useEffect, useMemo, useState } from 'react';
import { FormDialogScaffold } from '@/components/common/FormDialogScaffold';
import { SearchableSelect } from '@/components/common/SearchableSelect';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { formatMatchTypeLabel } from '../lib/warrantyLabels';
import {
  KIND_RULE_MATCH_TYPES,
  KIND_RULE_MATCH_TYPE_LABEL,
  type KindRuleMatchType,
  type WarrantyKindRef,
  type WarrantyKindRuleRow,
  type WarrantyKindRuleUpdate,
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
  onSubmit: (body: WarrantyKindRuleUpdate) => Promise<void>;
  isSubmitting: boolean;
  error: string | null;
}) {
  const isEdit = !!initial;
  const [kindId, setKindId] = useState('');
  // Held as a RAW string, not `KindRuleMatchType`: AC-P24 is tolerant at read,
  // so an existing row may carry a match type outside the four this screen
  // knows, and the admin has to SEE it before deciding whether to touch it.
  const [matchType, setMatchType] = useState<string>('model_prefix');
  // Whether the admin actually chose a match type in THIS dialog session. On an
  // edit, an untouched field is left out of the PATCH entirely (partial
  // semantics) so the stored value cannot be silently rewritten by a picker the
  // admin never opened. Create always sends it - the field is required there.
  const [matchTypeTouched, setMatchTypeTouched] = useState(false);
  const [matchValue, setMatchValue] = useState('');
  const [priority, setPriority] = useState('0');

  useEffect(() => {
    if (!open) return;
    setMatchTypeTouched(false);
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

  const isKnownMatchType = (KIND_RULE_MATCH_TYPES as string[]).includes(matchType);

  /**
   * The four known types, plus - only while it IS the current value - the raw
   * stored one, so the trigger resolves to something the admin can read instead
   * of falling back to the placeholder. `formatMatchTypeLabel` prints the raw
   * value for an unknown type by design; nothing is invented here.
   */
  const matchTypeOptions = useMemo(() => {
    const known = KIND_RULE_MATCH_TYPES.map((t) => ({
      value: t as string,
      label: KIND_RULE_MATCH_TYPE_LABEL[t],
    }));
    if (matchType && !isKnownMatchType) {
      return [{ value: matchType, label: formatMatchTypeLabel(matchType) }, ...known];
    }
    return known;
  }, [matchType, isKnownMatchType]);

  // No example to show for a match type this screen does not know.
  const valuePlaceholder = VALUE_PLACEHOLDER[matchType as KindRuleMatchType] ?? undefined;

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
        const body: WarrantyKindRuleUpdate = {
          kind_id: kindId,
          match_value: matchValue.trim(),
          priority: Number(priority) || 0,
        };
        // Create is strict (the field is required); an edit sends it only when
        // the admin actually chose one.
        if (!isEdit || matchTypeTouched) {
          body.match_type = matchType as KindRuleMatchType;
        }
        await onSubmit(body);
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
            onChange={(v) => {
              if (v === matchType) return;
              setMatchType(v);
              setMatchTypeTouched(true);
            }}
            options={matchTypeOptions}
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
              placeholder={valuePlaceholder}
              rows={3}
            />
          ) : (
            <Input
              id="rule-value"
              value={matchValue}
              onChange={(e) => setMatchValue(e.target.value)}
              placeholder={valuePlaceholder}
              autoComplete="off"
            />
          )}
        </div>
      </div>
    </FormDialogScaffold>
  );
}
