/**
 * Who is holding (or who held) a conversation SLA row, as a human name.
 *
 * Resolving a conversation ticket NULLs `assigned_to_id` by design, so a
 * resolved row has no assignee to show and every "Assigned to" surface reads
 * "-" on exactly the rows someone is looking at to find out who answered.
 * One rule for both surfaces (listing cell + detail header): an OPEN row names
 * its assignee, a RESOLVED row names its resolver.
 *
 * No UUIDs reach the screen: the backend falls back to the raw `resolved_by` /
 * `assigned_to` column when no user matches the id, so an id-shaped value is
 * treated as "unknown" rather than printed.
 */

export interface SlaHandlerSource {
  is_resolved?: boolean | null;
  assigned_user_name?: string | null;
  assigned_user?: { name?: string | null; email?: string | null } | null;
  assigned_to?: string | null;
  resolved_by_user_name?: string | null;
  resolved_by?: string | null;
}

export interface SlaHandler {
  /** Label for the name, so the reader knows which role they are looking at. */
  prefix: 'Assigned to' | 'Resolved by';
  /** Human-readable name/email, or null when nobody can be named. */
  name: string | null;
}

const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

function firstHumanValue(candidates: (string | null | undefined)[]): string | null {
  for (const candidate of candidates) {
    const value = (candidate ?? '').trim();
    if (!value) continue;
    if (UUID_RE.test(value)) continue;
    return value;
  }
  return null;
}

export function slaHandler(row: SlaHandlerSource): SlaHandler {
  if (row.is_resolved) {
    return {
      prefix: 'Resolved by',
      name: firstHumanValue([row.resolved_by_user_name, row.resolved_by]),
    };
  }
  return {
    prefix: 'Assigned to',
    name: firstHumanValue([
      row.assigned_user_name,
      row.assigned_user?.name,
      row.assigned_user?.email,
      row.assigned_to,
    ]),
  };
}
