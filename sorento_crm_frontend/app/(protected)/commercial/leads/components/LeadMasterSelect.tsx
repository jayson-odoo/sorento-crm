'use client';

import { useMemo } from 'react';
import { Label } from '@/components/ui/label';
import { SearchableSelect } from './SearchableSelect';
import type { AssignmentSelectOption } from '../services/leadQualificationMasterService';
import { optionListWithValue } from '../hooks/useLeadAssignmentSelect';
import { cn } from '@/lib/utils';

export const ASSIGN_EMPTY = '__lead_assign_empty__';

const stackWrap =
  'min-w-0 overflow-hidden rounded-[4px] border border-[#d1d5dc] bg-background [&_button]:h-[38px] [&_button]:rounded-none [&_button]:border-0 [&_button]:shadow-none';

/** Lead edit card — label + bordered control (matches StackField). */
export function LeadMasterStackSelect({
  label,
  htmlFor,
  value,
  onValueChange,
  options,
  loading,
  placeholder = 'Select…',
}: {
  label: string;
  htmlFor: string;
  value: string;
  onValueChange: (v: string) => void;
  options: AssignmentSelectOption[];
  loading?: boolean;
  placeholder?: string;
}) {
  const withValue = optionListWithValue(options, value);
  const searchOptions = useMemo(
    () => [
      { value: ASSIGN_EMPTY, label: placeholder },
      ...withValue.map((o) => ({ value: o.code, label: o.label })),
    ],
    [withValue, placeholder],
  );
  const v = value.trim() ? value : ASSIGN_EMPTY;
  return (
    <div className="flex flex-col gap-2">
      <Label htmlFor={htmlFor} className="text-[#4a5565] text-sm font-medium leading-5">
        {label}
      </Label>
      <div className={stackWrap} id={htmlFor}>
        <SearchableSelect
          value={v}
          onValueChange={(nv) => onValueChange(nv === ASSIGN_EMPTY ? '' : nv)}
          options={searchOptions}
          placeholder={loading ? 'Loading…' : placeholder}
          disabled={loading}
        />
      </div>
    </div>
  );
}

/** Create-lead wizard — plain FieldColumn styling. */
export function LeadMasterFieldSelect({
  label,
  value,
  onValueChange,
  options,
  loading,
  triggerClassName,
  placeholder = 'Select…',
}: {
  label: string;
  value: string;
  onValueChange: (v: string) => void;
  options: AssignmentSelectOption[];
  loading?: boolean;
  triggerClassName?: string;
  placeholder?: string;
}) {
  const withValue = optionListWithValue(options, value);
  const searchOptions = useMemo(
    () => [
      { value: ASSIGN_EMPTY, label: placeholder },
      ...withValue.map((o) => ({ value: o.code, label: o.label })),
    ],
    [withValue, placeholder],
  );
  const v = value.trim() ? value : ASSIGN_EMPTY;
  return (
    <div className="flex flex-col gap-2">
      <Label className="text-[#364153] text-sm font-medium leading-5">{label}</Label>
      <SearchableSelect
        value={v}
        onValueChange={(nv) => onValueChange(nv === ASSIGN_EMPTY ? '' : nv)}
        options={searchOptions}
        placeholder={loading ? 'Loading…' : placeholder}
        disabled={loading}
        className={cn(
          'h-[38px] w-full rounded-[4px] border border-[#d1d5dc] bg-background shadow-none focus:ring-1',
          triggerClassName,
        )}
      />
    </div>
  );
}
