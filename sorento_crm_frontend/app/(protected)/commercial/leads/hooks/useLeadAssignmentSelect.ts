import { useQuery } from '@tanstack/react-query';
import {
  fetchLeadAssignmentSelect,
  type AssignmentSelectOption,
  type LeadAssignmentKey,
} from '../services/leadQualificationMasterService';

export function useLeadAssignmentSelect(key: LeadAssignmentKey, enabled = true) {
  return useQuery({
    queryKey: ['lead-assignment-select', key],
    queryFn: () => fetchLeadAssignmentSelect(key),
    staleTime: 60_000,
    enabled,
  });
}

/** Renders selects when options may be empty but a legacy value must stay selectable. */
export function optionListWithValue(
  options: AssignmentSelectOption[],
  rawValue: string,
): AssignmentSelectOption[] {
  const v = rawValue.trim();
  if (!v) return options;
  const codes = new Set(options.map((o) => o.code));
  if (codes.has(v)) return options;
  return [...options, { code: v, label: `${v} (saved)` }];
}
