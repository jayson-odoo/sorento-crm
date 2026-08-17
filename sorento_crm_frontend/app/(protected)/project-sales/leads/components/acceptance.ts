/**
 * Presentation helpers for the informant and the acceptance handshake.
 *
 * Pure functions on purpose: the wait is the signal this slice exists to make visible,
 * and it has to read the same on a card, a detail header and a grid row.
 */
import { parseDateTimeAsUTC } from '@/lib/helpers';
import type {
  AcceptanceState,
  InformantSource,
  LeadInformantFields,
  LeadWithAcceptance,
} from '../../_shared/types/leadAcceptance.types';

/**
 * Every bucket the server takes. All of them are offered rather than a subset: a lead
 * recorded as `panel` or `contractor` has to be editable without the picker silently
 * resetting a source it cannot show.
 */
export const INFORMANT_SOURCE_OPTIONS: { value: InformantSource; label: string }[] = [
  { value: 'bci', label: 'BCI' },
  { value: 'panel', label: 'Panel' },
  { value: 'referral', label: 'Referral' },
  { value: 'walk_in', label: 'Walk in' },
  { value: 'consultant', label: 'Consultant' },
  { value: 'architect', label: 'Architect' },
  { value: 'contractor', label: 'Contractor' },
  { value: 'other', label: 'Other' },
];

/** An unrecognised code is humanised rather than shown raw. */
export function informantSourceLabel(source?: InformantSource | null): string | null {
  if (!source) return null;
  const known = INFORMANT_SOURCE_OPTIONS.find((option) => option.value === source);
  if (known) return known.label;
  const words = String(source).replace(/_/g, ' ');
  return words.charAt(0).toUpperCase() + words.slice(1);
}

/**
 * One line naming the informant. The firm when we have one, the person when we do not,
 * and the source alone when that is all anybody wrote down.
 */
export function informantSummary(lead: LeadInformantFields): string | null {
  const who = [lead.informant_party_label, lead.informant_contact_name]
    .filter(Boolean)
    .join(', ');
  const source = informantSourceLabel(lead.informant_source);
  const parts = [who || null, source, lead.informant_ref || null].filter(Boolean);
  return parts.length > 0 ? parts.join(' · ') : null;
}

export const ACCEPTANCE_LABELS: Record<AcceptanceState, string> = {
  assigned: 'Awaiting acceptance',
  accepted: 'Accepted',
  declined: 'Declined',
};

export function acceptanceLabel(
  lead: Pick<LeadWithAcceptance, 'acceptance_state' | 'owner_name'>,
): string {
  const state = lead.acceptance_state;
  if (!state) return 'Not assigned';
  if (state === 'assigned') {
    return lead.owner_name
      ? `Awaiting acceptance by ${lead.owner_name}`
      : ACCEPTANCE_LABELS.assigned;
  }
  if (state === 'accepted') {
    return lead.owner_name ? `Accepted by ${lead.owner_name}` : ACCEPTANCE_LABELS.accepted;
  }
  return ACCEPTANCE_LABELS.declined;
}

export function acceptanceBadgeVariant(
  state?: AcceptanceState | null,
): 'outline' | 'warning' | 'success' | 'destructive' {
  if (state === 'accepted') return 'success';
  if (state === 'assigned') return 'warning';
  if (state === 'declined') return 'destructive';
  return 'outline';
}

/**
 * Whether this viewer may hand the lead to somebody.
 *
 * Shared by the list row and the detail header so the two cannot drift: the server also
 * lets the person who RECORDED the lead hand it out, which is the decline path, since a
 * declined lead lands back with marketing owning nothing. The response carries no
 * `created_by`, so an unassigned lead is treated as assignable and the server has the
 * final say.
 */
export function canAssignLead(
  lead: Pick<LeadWithAcceptance, 'outcome' | 'can_edit' | 'owner_user_id'>,
): boolean {
  return lead.outcome === 'open' && (lead.can_edit || !lead.owner_user_id);
}

/**
 * The wait in plain words. Rounded down, because "3 hours" is a fact a person can act on
 * and "3.4 hours" is a number they have to translate first.
 */
export function describeWait(hours?: number | null): string | null {
  if (hours === null || hours === undefined || Number.isNaN(hours)) return null;
  if (hours < 1) return 'Under an hour';
  if (hours < 24) {
    const whole = Math.floor(hours);
    return `${whole} hour${whole === 1 ? '' : 's'}`;
  }
  const days = Math.floor(hours / 24);
  return `${days} day${days === 1 ? '' : 's'}`;
}

/** Hours since a naive-UTC timestamp, for screens the server did not hand a number to. */
export function hoursSince(timestamp?: string | null): number | null {
  if (!timestamp) return null;
  const then = parseDateTimeAsUTC(timestamp).getTime();
  if (Number.isNaN(then)) return null;
  return Math.max(0, (Date.now() - then) / 3_600_000);
}
