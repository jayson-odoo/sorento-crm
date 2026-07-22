'use client';

import { SearchableSelect } from '@/components/common/SearchableSelect';

export type GroupByOption = { value: string; label: string };

export function GroupBySelect({
  value,
  onChange,
  options,
  placeholder = 'Group by',
  className,
}: {
  value: string;
  onChange: (v: string) => void;
  options: GroupByOption[];
  placeholder?: string;
  className?: string;
}) {
  return (
    <SearchableSelect
      value={value}
      onChange={onChange}
      options={[
        { value: '__none__', label: 'No grouping' },
        ...options.map((o) => ({ value: o.value, label: `Group by ${o.label}` })),
      ]}
      placeholder={placeholder}
      triggerClassName={className ?? 'w-[200px]'}
    />
  );
}

export type GroupedRows<T> = { key: string; label: string; rows: T[] };

export function groupRowsBy<T extends Record<string, unknown>>(
  rows: T[],
  keyField: string,
  labelField: string,
  emptyLabel = 'Unassigned',
): GroupedRows<T>[] {
  const map = new Map<string, GroupedRows<T>>();
  for (const row of rows) {
    const rawKey = (row[keyField] as string | null | undefined) ?? '';
    const rawLabel =
      (row[labelField] as string | null | undefined) ?? (rawKey || emptyLabel);
    const key = rawKey || '__none__';
    const label = (rawLabel || '').trim() || emptyLabel;
    const existing = map.get(key);
    if (existing) {
      existing.rows.push(row);
    } else {
      map.set(key, { key, label, rows: [row] });
    }
  }
  return Array.from(map.values()).sort((a, b) => a.label.localeCompare(b.label));
}
