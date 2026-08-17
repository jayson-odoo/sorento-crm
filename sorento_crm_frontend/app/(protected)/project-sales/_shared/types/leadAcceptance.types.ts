/**
 * P1 - the informant and the acceptance handshake.
 *
 * Two ideas the rest of the slice depends on:
 *
 * - The INFORMANT is who told us. It is a data source, never a counterparty: a BCI
 *   sighting has no buyer at all, and writing BCI into `customers` would put a data
 *   vendor in the debtor ledger.
 * - The BUYER (`customer_id`) is therefore OPTIONAL. It becomes known when a contractor
 *   is awarded, which is usually weeks after the lead was worth recording.
 *
 * Assignment is not ownership. A lead is `assigned` until the salesperson accepts it, so
 * silence is visible instead of looking like quiet ownership.
 *
 * Shapes here mirror `documentation/plans/CONTRACT-project-lead-to-so.md` section 1.
 */
import type { DataGridParamsInput } from '@/lib/api-client';
import type { ProjectLead } from './project.types';

/**
 * Every bucket the server accepts. Wider than the contract's original list because the
 * contract and the UAC disagreed; the API takes the union, so the UI must be able to
 * RENDER all of them (an older lead may carry `panel` or `contractor`) and must never
 * validate against a shorter list.
 */
export type InformantSource =
  | 'bci'
  | 'panel'
  | 'referral'
  | 'walk_in'
  | 'consultant'
  | 'architect'
  | 'contractor'
  | 'other';

export type AcceptanceState = 'assigned' | 'accepted' | 'declined';

/** Response fields added to `ProjectLeadResponse` by P1. */
export interface LeadInformantFields {
  informant_source?: InformantSource | null;
  /** Their reference, e.g. a BCI job id. */
  informant_ref?: string | null;
  informant_party_id?: string | null;
  /** Resolved firm name. The UI renders this, never the id. */
  informant_party_label?: string | null;
  /** A lone informant with no firm on record is normal. */
  informant_contact_name?: string | null;
}

export interface LeadAcceptanceFields {
  acceptance_state?: AcceptanceState | null;
  assigned_at?: string | null;
  accepted_at?: string | null;
  declined_reason?: string | null;
  declined_at?: string | null;
}

/**
 * A lead as P1 serves it. `customer_id` is widened to nullable here because it is the
 * BUYER now, and phase 1 typed it as required.
 */
export type LeadWithAcceptance = Omit<ProjectLead, 'customer_id'> &
  LeadInformantFields &
  LeadAcceptanceFields & {
    customer_id?: string | null;
  };

/** Row of the marketing worklist. The wait arrives computed, so no date maths here. */
export type AwaitingAcceptanceRow = LeadWithAcceptance & {
  hours_since_assigned: number;
};

/** Accepted by POST and PUT on `/leads`. */
export interface LeadInformantBody {
  informant_source?: InformantSource | null;
  informant_ref?: string | null;
  informant_party_id?: string | null;
  informant_contact_name?: string | null;
}

export interface AssignLeadBody {
  owner_user_id: string;
  note?: string | null;
}

export interface DeclineLeadBody {
  reason: string;
}

export interface AwaitingAcceptanceParams extends DataGridParamsInput {
  owner_user_id?: string;
  min_hours?: number;
}

/** `{data, total, page, limit}`, per the phase-2 list contract. */
export interface AwaitingAcceptanceEnvelope {
  data: AwaitingAcceptanceRow[];
  total: number;
  page: number;
  limit: number;
}
