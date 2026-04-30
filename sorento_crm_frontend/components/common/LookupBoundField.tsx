'use client';

import { useMemo } from 'react';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { useLookupOptionsByBinding } from '@/hooks/useLookupOptionsByBinding';

export interface LookupBoundFieldProps {
  table: string;
  column: string;
  value: string | null | undefined;
  onChange: (next: string) => void;
  placeholder?: string;
  renderFallback: () => React.ReactNode;
}

export default function LookupBoundField({
  table,
  column,
  value,
  onChange,
  placeholder,
  renderFallback,
}: LookupBoundFieldProps) {
  const { data, isLoading } = useLookupOptionsByBinding(table, column);

  const hasBinding = !!data?.set_key;
  const options = useMemo(() => data?.options ?? [], [data]);

  if (isLoading || !data) return <>{renderFallback()}</>;
  if (!hasBinding) return <>{renderFallback()}</>;

  const current = value ?? '';
  const matches = options.some((o) => o.value === current);

  return (
    <Select value={matches ? current : ''} onValueChange={onChange}>
      <SelectTrigger>
        <SelectValue placeholder={placeholder ?? 'Select…'} />
      </SelectTrigger>
      <SelectContent>
        {!matches && current ? (
          <SelectItem value={current} disabled>
            {current} (legacy)
          </SelectItem>
        ) : null}
        {options.map((o) => (
          <SelectItem key={o.value} value={o.value}>
            {o.label}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}
