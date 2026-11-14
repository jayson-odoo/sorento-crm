import type { MatchType } from '../types/warranty.types';

const ISO = /^(\d{4})-(\d{2})-(\d{2})$/;

/** '2026-09-01' -> '01/09/2026'. A civil date: never passed through a Date, so no timezone shift. */
export function formatCivilDate(iso: string | null | undefined): string {
  if (!iso) return '-';
  const m = ISO.exec(iso);
  return m ? `${m[3]}/${m[2]}/${m[1]}` : iso;
}

function shift(iso: string | null | undefined, days: number): string | null {
  const m = iso ? ISO.exec(iso) : null;
  if (!m) return null;
  const d = new Date(Date.UTC(Number(m[1]), Number(m[2]) - 1, Number(m[3]) + days));
  return d.toISOString().slice(0, 10);
}

export const nextCivilDay = (iso: string | null | undefined) => shift(iso, 1);
export const previousCivilDay = (iso: string | null | undefined) => shift(iso, -1);

export type PolicyLifecycle = 'in_force' | 'scheduled' | 'superseded';

export const POLICY_LIFECYCLE_LABEL: Record<PolicyLifecycle, string> = {
  in_force: 'In force',
  scheduled: 'Scheduled',
  superseded: 'Superseded',
};

function todayCivil(): string {
  const now = new Date();
  const mm = String(now.getMonth() + 1).padStart(2, '0');
  const dd = String(now.getDate()).padStart(2, '0');
  return `${now.getFullYear()}-${mm}-${dd}`;
}

/** Both ends inclusive: it is in force on its first and its last day. */
export function policyLifecycle(p: { effective_from: string; effective_to: string | null }): PolicyLifecycle {
  const today = todayCivil();
  if (p.effective_from > today) return 'scheduled';
  if (p.effective_to && p.effective_to < today) return 'superseded';
  return 'in_force';
}

const MATCH_TYPE_LABEL: Record<MatchType, string> = {
  series: 'Series',
  model_list: 'Model list',
  category: 'Category',
  code_prefix: 'Code prefix',
};

export const MATCH_TYPES = Object.keys(MATCH_TYPE_LABEL) as MatchType[];

export function formatMatchTypeLabel(type: string): string {
  return MATCH_TYPE_LABEL[type as MatchType] ?? type;
}
