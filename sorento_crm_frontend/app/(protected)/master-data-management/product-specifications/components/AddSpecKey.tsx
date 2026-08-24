'use client';

import { useState } from 'react';
import { Alert, AlertIcon, AlertTitle } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { SearchableSelect } from '@/components/common/SearchableSelect';
import { createSpecKey } from '../services/productSpecService';
import type { SpecRegistryKey } from '../types/productSpec.types';

// "Dropdown" is the captain's word for the fixed-list type: it names the control the
// user actually sees. Kept in lockstep with the product page's AddSpecificationDialog
// so the same type never has two names.
const DATA_TYPES = [
  { value: 'enum', label: 'Dropdown (a finish, a mounting)' },
  { value: 'numeric', label: 'A measurement or a count' },
  { value: 'boolean', label: 'Yes or no (it has one, or it does not)' },
];

/** `bowl_count` from "Number of bowls" - the key the chatbot and the parser share. */
function toKey(label: string): string {
  return label
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '_')
    .replace(/^_+|_+$/g, '')
    .replace(/^([0-9])/, 'k$1');
}

/**
 * Add a specification the catalogue does not have yet.
 *
 * Deliberately asks for the least it can. A new key is useless until it has rules that
 * read it out of a product and words customers say for it, and both of those are edited
 * on the key itself - so this collects the name and the shape, then hands straight over
 * rather than presenting a long form nobody can complete in one sitting.
 */
export default function AddSpecKey({
  open,
  onOpenChange,
  onCreated,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onCreated: (key: SpecRegistryKey) => void;
}) {
  const [label, setLabel] = useState('');
  const [dataType, setDataType] = useState('enum');
  const [unit, setUnit] = useState('');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const specKey = toKey(label);

  const reset = () => {
    setLabel('');
    setDataType('enum');
    setUnit('');
    setError(null);
  };

  const save = async () => {
    setSaving(true);
    setError(null);
    try {
      const created = await createSpecKey({
        spec_key: specKey,
        label: label.trim(),
        data_type: dataType,
        unit: dataType === 'numeric' && unit.trim() ? unit.trim() : null,
      });
      onCreated(created);
      reset();
      onOpenChange(false);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not add the specification');
    } finally {
      setSaving(false);
    }
  };

  if (!open) return null;

  return (
    <div className="mb-4 flex w-full flex-col gap-3 rounded-md border bg-muted/20 p-4">
      {error && (
        <Alert variant="destructive">
          <AlertIcon />
          <AlertTitle>{error}</AlertTitle>
        </Alert>
      )}

      <div className="flex flex-wrap items-end gap-3">
        <div className="min-w-[14rem] flex-1">
          <label htmlFor="new-spec-label" className="mb-1 block text-xs uppercase tracking-wide text-muted-foreground">
            What staff call it
          </label>
          <Input
            id="new-spec-label"
            value={label}
            placeholder="Rough-in distance"
            onChange={(e) => setLabel(e.target.value)}
          />
        </div>
        <div className="min-w-[16rem] flex-1">
          <label className="mb-1 block text-xs uppercase tracking-wide text-muted-foreground">
            What kind of value
          </label>
          <SearchableSelect value={dataType} onChange={setDataType} options={DATA_TYPES} />
        </div>
        {dataType === 'numeric' && (
          <div className="w-28">
            <label htmlFor="new-spec-unit" className="mb-1 block text-xs uppercase tracking-wide text-muted-foreground">
              Unit
            </label>
            <Input
              id="new-spec-unit"
              value={unit}
              placeholder="mm"
              onChange={(e) => setUnit(e.target.value)}
            />
          </div>
        )}
      </div>

      {label.trim() && (
        <p className="text-xs text-muted-foreground">
          The chatbot and the parser will both know it as{' '}
          <span className="font-mono">{specKey}</span>.
        </p>
      )}

      <p className="text-xs text-muted-foreground">
        Once it exists, open it and add the rules that read it out of a product - until
        then it is a name with nothing behind it. Products only carry the new value after
        the catalogue is derived again.
      </p>

      <div className="flex gap-2">
        <Button size="sm" onClick={save} disabled={!label.trim() || saving}>
          {saving ? 'Adding…' : 'Add specification'}
        </Button>
        <Button
          size="sm"
          variant="outline"
          onClick={() => {
            reset();
            onOpenChange(false);
          }}
          disabled={saving}
        >
          Cancel
        </Button>
      </div>
    </div>
  );
}
