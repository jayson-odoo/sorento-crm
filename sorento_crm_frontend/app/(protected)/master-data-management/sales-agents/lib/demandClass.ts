/**
 * The demand classes the fulfilment policy can weigh, mirrored from the backend's
 * `app/services/scm/demand_class.py`.
 *
 * Closed on purpose: the backend refuses any other word. `other` is shown "Other" and
 * plans as retail in SCM. Unset is a real choice - "not a
 * project" and "nobody said" mean opposite things - which is why the select is
 * clearable rather than defaulted.
 */
import type { SearchableSelectOption } from '@/components/common/SearchableSelect';

export const DEMAND_CLASSES = ['project', 'retail', 'other'] as const;

export type DemandClass = (typeof DEMAND_CLASSES)[number];

export const DEMAND_CLASS_LABEL: Record<string, string> = {
  project: 'Project',
  retail: 'Retail',
  other: 'Other',
};

export const DEMAND_CLASS_OPTIONS: SearchableSelectOption[] = DEMAND_CLASSES.map((value) => ({
  value,
  label: DEMAND_CLASS_LABEL[value],
}));

/** The label for a stored value, falling back to the raw value for anything unknown. */
export function demandClassLabel(value: string | null | undefined): string | null {
  if (!value) return null;
  return DEMAND_CLASS_LABEL[value] ?? value;
}
