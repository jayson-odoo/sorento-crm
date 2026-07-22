'use client';

import { useEffect, useState } from 'react';
import { X } from 'lucide-react';
import { SearchableSelect } from '@/components/common/SearchableSelect';
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
        if (!cancelled) setOptions(data.options);
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
    <div className="relative">
      <SearchableSelect
        key={value || 'empty'}
        id={id}
        value={value || ''}
        onChange={(v) => onChange(v)}
        disabled={disabled || loading}
        options={options.map((opt) => ({ value: opt.value, label: opt.label }))}
        placeholder={placeholder ?? 'Select...'}
        triggerClassName="w-full pr-12"
      />
      {value && !disabled && !loading && (
        <button
          type="button"
          aria-label="Clear selection"
          className="absolute right-7 top-1/2 -translate-y-1/2 p-0.5 rounded text-muted-foreground hover:text-foreground hover:bg-accent z-10"
          onPointerDown={(e) => {
            e.preventDefault();
            e.stopPropagation();
          }}
          onMouseDown={(e) => {
            e.preventDefault();
            e.stopPropagation();
          }}
          onClick={(e) => {
            e.preventDefault();
            e.stopPropagation();
            onChange('');
          }}
        >
          <X className="h-3.5 w-3.5" />
        </button>
      )}
    </div>
  );
}
