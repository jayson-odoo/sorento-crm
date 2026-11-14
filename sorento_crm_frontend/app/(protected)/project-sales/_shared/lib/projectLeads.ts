import type { Project, TakeoverRequest } from '../types/project.types';

/**
 * One row of a project's leads list on the Access card (PROJECT-LEADS-REASSIGN B1-B3, B6, B8).
 *
 * `lead` is blank for a current owner who is neither the primary nor a secondary lead; `status`
 * is set only for a secondary lead still waiting (pending) or turned down (rejected).
 */
export interface ProjectLeadRow {
  id: string;
  userId: string;
  name: string;
  lead: 'Primary' | 'Secondary' | null;
  date: string | null;
  foundBy: string | null;
  isOwner: boolean;
  status: 'pending' | 'rejected' | null;
  requestId: string | null;
  inactive: boolean;
}

/**
 * The primary first, then every secondary lead (a dispute request, pending or decided), earliest
 * find first (an undated one last), plus the current owner when they are neither. A join request is not a lead.
 *
 * Primary Date is the lead raised date when the project came from a lead, else the registration
 * date; its "How they found it" is the lead source label. A secondary lead's are its request date
 * and its own note. Owner is marked once, on the person's first row.
 *
 * `activeUserIds`, when known, marks anyone not in it as inactive; omitted, nobody is.
 */
export function buildProjectLeads(
  project: Project,
  requests: TakeoverRequest[],
  sourceLabel: string | null,
  activeUserIds?: Set<string> | null,
): ProjectLeadRow[] {
  const isInactive = (userId: string) => Boolean(activeUserIds) && !activeUserIds!.has(userId);
  const rows: ProjectLeadRow[] = [];

  if (project.primary_owner_user_id) {
    rows.push({
      id: 'primary',
      userId: project.primary_owner_user_id,
      name: project.primary_owner_name ?? 'Unknown user',
      lead: 'Primary',
      date: project.lead_id ? (project.lead_created_at ?? null) : (project.created_at ?? null),
      foundBy: sourceLabel,
      isOwner: false,
      status: null,
      requestId: null,
      inactive: isInactive(project.primary_owner_user_id),
    });
  }

  const secondaries = requests
    .filter((request) => request.kind === 'dispute')
    .map((request, index) => ({ request, index }))
    .sort((a, b) => {
      const at = a.request.created_at ? Date.parse(a.request.created_at) : Number.POSITIVE_INFINITY;
      const bt = b.request.created_at ? Date.parse(b.request.created_at) : Number.POSITIVE_INFINITY;
      return at === bt ? a.index - b.index : at - bt;
    })
    .map(({ request }) => request);
  for (const request of secondaries) {
    rows.push({
      id: request.id,
      userId: request.requester_user_id,
      name: request.requester_name ?? 'Unknown user',
      lead: 'Secondary',
      date: request.created_at ?? null,
      foundBy: request.reason || null,
      isOwner: false,
      status: request.status === 'approved' ? null : request.status,
      requestId: request.id,
      inactive: isInactive(request.requester_user_id),
    });
  }

  const ownerId = project.owner_user_id;
  if (ownerId) {
    const first = rows.find((row) => row.userId === ownerId);
    if (first) first.isOwner = true;
    else
      rows.push({
        id: 'owner',
        userId: ownerId,
        name: project.owner_name ?? 'Unknown user',
        lead: null,
        date: null,
        foundBy: null,
        isOwner: true,
        status: null,
        requestId: null,
        inactive: isInactive(ownerId),
      });
  }

  return rows;
}
