/**
 * Display helpers for the warranty configuration area.
 *
 * `effective_from` / `effective_to` are Postgres DATE columns - civil days, not
 * instants. They are formatted by SPLITTING THE STRING rather than by going
 * through `new Date(...)`: `new Date('2000-01-01')` is parsed as UTC midnight
 * and renders as the previous day anywhere west of Greenwich, which would put a
 * policy window off by one for a reader in another timezone.
 */
import type { WarrantyPolicyRow, WarrantyTermRow } from '../types/warranty-config.types';

const MONTHS = [
  'Jan',
  'Feb',
  'Mar',
  'Apr',
  'May',
  'Jun',
  'Jul',
  'Aug',
  'Sep',
  'Oct',
  'Nov',
  'Dec',
];

/** `2000-01-01` -> `01 Jan 2000`. Returns the input unchanged if it is not a date. */
export function formatCivilDate(iso: string | null | undefined): string {
  if (!iso) return '-';
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso);
  if (!m) return iso;
  const [, y, mo, d] = m;
  return `${d} ${MONTHS[Number(mo) - 1] ?? mo} ${y}`;
}

/** The policy window, both ends inclusive, open-ended when there is no end. */
export function formatEffectiveRange(policy: WarrantyPolicyRow): string {
  return policy.effective_to
    ? `${formatCivilDate(policy.effective_from)} - ${formatCivilDate(policy.effective_to)}`
    : `${formatCivilDate(policy.effective_from)} onwards`;
}

/** Today, as a civil `YYYY-MM-DD`, for comparing against a DATE column. */
function todayCivil(): string {
  const now = new Date();
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`;
}

/** Whether the policy governs a purchase made today. Both ends INCLUSIVE (AC-P2b). */
export function isInForceToday(policy: WarrantyPolicyRow): boolean {
  const today = todayCivil();
  return policy.effective_from <= today && (policy.effective_to === null || policy.effective_to >= today);
}

export type PolicyLifecycle = 'in_force' | 'scheduled' | 'superseded';

/**
 * Three states, not two. Supersede publishes the successor with a FUTURE
 * `effective_from`, so between publishing and that date the new version is
 * neither in force nor superseded - and labelling a policy that has not started
 * yet "Superseded" tells an admin the opposite of what happened.
 */
export function policyLifecycle(policy: WarrantyPolicyRow): PolicyLifecycle {
  const today = todayCivil();
  if (policy.effective_from > today) return 'scheduled';
  return isInForceToday(policy) ? 'in_force' : 'superseded';
}

export const POLICY_LIFECYCLE_LABEL: Record<PolicyLifecycle, string> = {
  in_force: 'In force',
  scheduled: 'Scheduled',
  superseded: 'Superseded',
};

export const POLICY_LIFECYCLE_BADGE: Record<PolicyLifecycle, 'success' | 'info' | 'secondary'> = {
  in_force: 'success',
  scheduled: 'info',
  superseded: 'secondary',
};

/** `60` -> `5 years`; `24` -> `2 years`; `18` -> `18 months`. */
export function formatMonths(months: number): string {
  if (months % 12 === 0) {
    const years = months / 12;
    return `${years} year${years === 1 ? '' : 's'}`;
  }
  return `${months} month${months === 1 ? '' : 's'}`;
}

/** What the Term promises, as one string. */
export function formatCoverage(term: WarrantyTermRow): string {
  if (term.is_lifetime) return 'Lifetime';
  if (term.duration_months == null) return '-';
  const base = formatMonths(term.duration_months);
  if (term.registration_bonus_months) {
    return `${base} + ${formatMonths(term.registration_bonus_months)} on registration`;
  }
  return base;
}

/** What defects the Term covers. NULL and [] are identical: every defect. */
export function formatDefectScope(term: WarrantyTermRow): string {
  const labels = term.covered_defect_type_labels;
  if (!labels || labels.length === 0) return 'All defect types';
  return labels.join(', ');
}
