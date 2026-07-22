'use client';

import { SearchableSelect } from '@/components/common/SearchableSelect';
import { Layers } from 'lucide-react';

export interface GroupByOption<T extends string = string> {
  value: T;
  label: string;
}

interface GroupBySelectProps<T extends string = string> {
  /** Current value: use 'none' or '' for no grouping (flat list). */
  value: T | 'none' | '';
  options: GroupByOption<T>[];
  onValueChange: (value: T | 'none') => void;
  placeholder?: string;
  /** Label for the "no grouping" option when not in options. */
  allLabel?: string;
  className?: string;
  size?: 'sm' | 'md' | 'lg';
}

/**
 * Reusable control for list views: switch between flat list (All) and grouped by a field.
 * Use with view state (e.g. groupBy: null | 'spo_number') and render list/flat or grouped accordingly.
 */
export function GroupBySelect<T extends string = string>({
  value,
  options,
  onValueChange,
  placeholder = 'View',
  allLabel = 'All',
  className,
  size = 'sm',
}: GroupBySelectProps<T>) {
  const normalizedValue = value === '' || value === 'none' ? '__none__' : value;

  return (
    <SearchableSelect
      value={normalizedValue}
      onChange={(v) => onValueChange((v === '__none__' ? 'none' : v) as T | 'none')}
      options={[
        { value: '__none__', label: allLabel },
        ...options.map((opt) => ({ value: opt.value, label: opt.label })),
      ]}
      placeholder={placeholder}
      size={size}
      triggerClassName={className}
      renderTriggerLabel={(opt) => (
        <span className="flex items-center">
          <Layers className="size-3.5 text-muted-foreground me-1.5 shrink-0" />
          {opt.label}
        </span>
      )}
    />
  );
}
