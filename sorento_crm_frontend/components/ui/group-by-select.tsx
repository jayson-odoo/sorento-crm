'use client';

import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
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
    <Select
      value={normalizedValue}
      onValueChange={(v) => onValueChange((v === '__none__' ? 'none' : v) as T | 'none')}
    >
      <SelectTrigger size={size} className={className}>
        <Layers className="size-3.5 text-muted-foreground me-1.5 shrink-0" />
        <SelectValue placeholder={placeholder} />
      </SelectTrigger>
      <SelectContent>
        <SelectItem value="__none__">{allLabel}</SelectItem>
        {options.map((opt) => (
          <SelectItem key={opt.value} value={opt.value}>
            {opt.label}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}
