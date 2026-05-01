'use client';

import { useEffect, useState } from 'react';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { LookupSetOption, lookupSet } from '../lib/portal-client';

export interface LookupSelectProps {
  setKey: string;
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  disabled?: boolean;
  id?: string;
}

/**
 * Simple Select dropdown backed by /portal/lookups/sets/{setKey}.
 * Options are cached per setKey via the portal-client lookupSet helper.
 */
export function LookupSelect({
  setKey,
  value,
  onChange,
  placeholder,
  disabled,
  id,
}: LookupSelectProps) {
  const [options, setOptions] = useState<LookupSetOption[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    lookupSet(setKey)
      .then((data) => {
        if (!cancelled) setOptions(data);
      })
      .catch(() => {
        if (!cancelled) setOptions([]);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [setKey]);

  return (
    <Select
      value={value || undefined}
      onValueChange={(v) => onChange(v)}
      disabled={disabled || loading}
    >
      <SelectTrigger id={id} className="w-full">
        <SelectValue placeholder={placeholder ?? 'Select...'} />
      </SelectTrigger>
      <SelectContent>
        {options.map((opt) => (
          <SelectItem key={opt.value} value={opt.value}>
            {opt.label}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}
