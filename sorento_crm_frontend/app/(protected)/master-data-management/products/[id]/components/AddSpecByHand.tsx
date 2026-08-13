'use client';

import { useEffect, useMemo, useState } from 'react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { SearchableSelect } from '@/components/common/SearchableSelect';
import {
  getSpecRegistry,
  setSpecValueByHand,
} from '../../../product-specifications/services/productSpecService';
import { readable } from '../../../product-specifications/lib/readable';
import type { SpecRegistryKey } from '../../../product-specifications/types/productSpec.types';

/**
 * Set a specification this product's text never states.
 *
 * A blue WC is blue in the photograph and nowhere in the description or the flyer. No
 * rule can read it, so the only honest source is a person — and a value set here is
 * marked `human` and survives every later re-derivation rather than being overwritten
 * by the next catalogue run.
 *
 * The value still has to come from the registry: a hand-set spec that invented its own
 * word would be invisible to the ranker and to the chatbot parser, which is the whole
 * reason the vocabulary is shared.
 */
export default function AddSpecByHand({
  productId,
  onSaved,
  onCancel,
}: {
  productId: string;
  onSaved: () => void;
  onCancel: () => void;
}) {
  const [keys, setKeys] = useState<SpecRegistryKey[]>([]);
  const [specKey, setSpecKey] = useState('');
  const [value, setValue] = useState('');
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    getSpecRegistry()
      .then((r) => setKeys(r.keys))
      .catch(() => setKeys([]));
  }, []);

  const selected = useMemo(() => keys.find((k) => k.spec_key === specKey), [keys, specKey]);
  const choices = selected?.allowed_values ?? [];

  const save = async () => {
    if (!specKey || value === '') return;
    setSaving(true);
    try {
      await setSpecValueByHand(productId, specKey, value);
      toast.success(`${selected ? selected.label : readable(specKey)} set by hand`, {
        description: 'It will survive every later re-derivation.',
      });
      onSaved();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Could not save the value', {
        duration: 10_000,
      });
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="flex flex-wrap items-end gap-3 rounded-md border bg-muted/20 p-4">
      <div className="min-w-[14rem] flex-1">
        <label className="mb-1.5 block text-xs font-medium text-muted-foreground">
          Specification
        </label>
        <SearchableSelect
          value={specKey}
          onChange={(next) => {
            setSpecKey(next);
            setValue('');
          }}
          options={keys.map((k) => ({ value: k.spec_key, label: k.label || readable(k.spec_key) }))}
        />
      </div>

      <div className="min-w-[12rem] flex-1">
        <label className="mb-1.5 block text-xs font-medium text-muted-foreground">Value</label>
        {selected?.data_type === 'boolean' ? (
          <SearchableSelect
            value={value}
            onChange={setValue}
            options={[
              { value: 'true', label: 'Yes' },
              { value: 'false', label: 'No' },
            ]}
          />
        ) : choices.length > 0 ? (
          <SearchableSelect
            value={value}
            onChange={setValue}
            options={choices.map((v) => ({ value: v, label: readable(v) }))}
          />
        ) : (
          <Input
            value={value}
            onChange={(e) => setValue(e.target.value)}
            placeholder={selected?.unit ? `in ${selected.unit}` : 'value'}
            type={selected?.data_type === 'numeric' ? 'number' : 'text'}
          />
        )}
      </div>

      <div className="flex gap-2 pb-0.5">
        <Button size="sm" onClick={save} disabled={!specKey || value === '' || saving}>
          {saving ? 'Saving…' : 'Set by hand'}
        </Button>
        <Button size="sm" variant="outline" onClick={onCancel} disabled={saving}>
          Cancel
        </Button>
      </div>
    </div>
  );
}
