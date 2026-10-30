'use client';

import { useMemo } from 'react';

import { SearchableMultiSelect } from '@/components/common/SearchableMultiSelect';
import { Badge } from '@/components/ui/badge';
import { Label } from '@/components/ui/label';

/** The "No class" entry: products with no item class (backend `contact_brand_scope.NO_CLASS`). */
export const NO_CLASS = '__NONE__';

export interface ItemClassOption {
  value: string;
  label: string;
}

/**
 * The next allowed list after a pick. The first class picked into an empty list also ticks
 * "No class" (it can be unticked after), so a first pick never hides the unclassed products.
 */
export function nextAllowedClasses(previous: string[], picked: string[]): string[] {
  if (previous.length === 0 && picked.length > 0 && !picked.includes(NO_CLASS)) {
    return [NO_CLASS, ...picked];
  }
  return picked;
}

/**
 * Allowed item classes, one flat list under Brands (TAG-BRAND-CLASS). Shared by the contact
 * Profile > Brands card and the tag Access settings Brands row: empty = every class. Options are
 * class CODES (one per code across companies), "No class" first. A saved code the options no
 * longer carry shows as the code itself.
 */
export default function AllowedItemClassesPicker({
  id,
  value,
  onChange,
  options,
  editing = true,
  disabled = false,
  loadError,
  onRetry,
}: {
  id: string;
  value: string[];
  onChange: (codes: string[]) => void;
  options: ItemClassOption[];
  editing?: boolean;
  disabled?: boolean;
  loadError?: unknown;
  onRetry?: () => void;
}) {
  const merged = useMemo(() => {
    const extra = value
      .filter((code) => !options.some((o) => o.value === code))
      .map((code) => ({ value: code, label: code }));
    return [...options, ...extra];
  }, [options, value]);
  const labelOf = (code: string) => merged.find((o) => o.value === code)?.label ?? code;

  return (
    <div className="grid gap-2 ml-3.5 border-l-2 pl-3">
      <Label htmlFor={id} className="font-normal text-muted-foreground">
        Allowed item classes
      </Label>
      {editing ? (
        <SearchableMultiSelect
          id={id}
          value={value}
          onChange={(picked) => onChange(nextAllowedClasses(value, picked))}
          options={merged}
          placeholder="All classes"
          emptyMessage="No classes found"
          clearable
          loadError={loadError}
          onRetry={onRetry}
          disabled={disabled}
        />
      ) : value.length ? (
        <div className="flex flex-wrap gap-1">
          {value.map((code) => (
            <Badge key={code} variant="secondary" appearance="light" className="font-normal">
              {labelOf(code)}
            </Badge>
          ))}
        </div>
      ) : (
        <span className="text-sm text-muted-foreground">All classes</span>
      )}
    </div>
  );
}
