'use client';

import { useMemo, useState } from 'react';
import { ListFilter, X } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import { SearchableSelect } from '@/components/common/SearchableSelect';
import { readableValue } from '@/lib/spec-readable';
import type { IconCondition, SpecRegistryKey } from '../../types/productSpec.types';

/** The values another spec offers a condition: its vocabulary, yes/no, or the numbers products hold. */
function valueOptions(key: SpecRegistryKey): { value: string; label: string }[] {
  const labels = key.value_labels ?? {};
  const values =
    key.data_type === 'boolean'
      ? ['true', 'false']
      : key.data_type === 'numeric'
        ? key.numeric_values ?? []
        : key.allowed_values ?? [];
  return values.map((value) => ({
    value,
    label:
      key.data_type === 'boolean'
        ? value === 'true'
          ? 'Yes'
          : 'No'
        : readableValue(value, key.unit ?? undefined, labels),
  }));
}

/**
 * The "Only with" list of one icon chip (SPEC-ICON-COMBINED R1): other specs and one of their
 * values, all of which a product must hold for the icon to print. Edit mode only.
 */
export function IconConditionsPopover({
  iconName,
  hostKey,
  registry,
  conditions,
  onChange,
}: {
  iconName: string;
  hostKey: string;
  registry: readonly SpecRegistryKey[];
  conditions: IconCondition[];
  onChange: (next: IconCondition[]) => void;
}) {
  const [specKey, setSpecKey] = useState('');
  const [value, setValue] = useState('');
  const partners = useMemo(
    () =>
      registry.filter(
        (key) =>
          key.is_active !== false &&
          key.spec_key !== hostKey &&
          !conditions.some((c) => c.spec_key === key.spec_key),
      ),
    [registry, hostKey, conditions],
  );
  const partner = registry.find((key) => key.spec_key === specKey);
  const labelOf = (c: IconCondition) => {
    const key = registry.find((k) => k.spec_key === c.spec_key);
    if (!key) return `${c.spec_key} = ${c.value}`;
    const option = valueOptions(key).find((o) => o.value === c.value);
    return `${key.label} = ${option?.label ?? c.value}`;
  };

  return (
    <Popover>
      <PopoverTrigger asChild>
        <Button
          type="button"
          size="icon"
          variant={conditions.length > 0 ? 'secondary' : 'ghost'}
          className="size-7"
          aria-label={`Only with conditions for ${iconName}`}
          title={conditions.length > 0 ? conditions.map(labelOf).join(', ') : undefined}
        >
          <ListFilter className="size-3.5" />
        </Button>
      </PopoverTrigger>
      <PopoverContent className="flex w-72 flex-col gap-2 p-3">
        <span className="text-sm font-medium">Only with</span>
        {conditions.map((c) => (
          <div key={c.spec_key} className="flex items-center justify-between gap-2 text-sm">
            <span className="min-w-0 truncate" title={labelOf(c)}>
              {labelOf(c)}
            </span>
            <Button
              type="button"
              size="icon"
              variant="ghost"
              className="size-7 shrink-0"
              aria-label={`Remove condition ${labelOf(c)}`}
              onClick={() => onChange(conditions.filter((other) => other.spec_key !== c.spec_key))}
            >
              <X className="size-3.5" />
            </Button>
          </div>
        ))}
        <SearchableSelect
          value={specKey}
          onChange={(next) => {
            setSpecKey(next);
            setValue('');
          }}
          options={partners.map((key) => ({ value: key.spec_key, label: key.label }))}
          placeholder="Specification"
          clearable
        />
        {partner && (
          <SearchableSelect
            value={value}
            onChange={setValue}
            options={valueOptions(partner)}
            placeholder="Value"
            clearable
          />
        )}
        <Button
          type="button"
          size="sm"
          disabled={!specKey || !value}
          onClick={() => {
            onChange([...conditions, { spec_key: specKey, value }]);
            setSpecKey('');
            setValue('');
          }}
        >
          Add condition
        </Button>
      </PopoverContent>
    </Popover>
  );
}
