'use client';

import { Label } from '@/components/ui/label';
import { DateRangePicker } from '@/components/ui/date-range-picker';

export type LastActivityRange = { from?: string; to?: string };

type Props = {
  id: string;
  value: LastActivityRange;
  onChange: (next: LastActivityRange) => void;
};

/** The "Last activity" range every form list offers in its Filters panel (YYYY-MM-DD, Malaysia days). */
export function LastActivityFilter({ id, value, onChange }: Props) {
  return (
    <div>
      <Label htmlFor={id} className="mb-1 block">
        Last activity
      </Label>
      <DateRangePicker
        id={id}
        from={value.from || null}
        to={value.to || null}
        onChange={({ from, to }) => onChange({ from: from ?? undefined, to: to ?? undefined })}
        placeholder="All dates"
      />
    </div>
  );
}

/** Number of ends set, as one filter: 0 or 1. */
export function lastActivityActive(value: LastActivityRange): number {
  return value.from || value.to ? 1 : 0;
}

/** Short text for a filter summary pill, or '' when no range is set. */
export function lastActivityLabel(value: LastActivityRange): string {
  if (!value.from && !value.to) return '';
  const fmt = (iso: string) => iso.split('-').reverse().join('/');
  if (value.from && value.to) return `Last activity ${fmt(value.from)} - ${fmt(value.to)}`;
  return value.from ? `Last activity from ${fmt(value.from)}` : `Last activity to ${fmt(value.to as string)}`;
}
