/**
 * Catalogue Editions - the approval cycle over a page (S2.5).
 *
 * ---------------------------------------------------------------------------
 * CONTRACT - `app/api/v1/dealer_kit/editions.py`, all under `/api/v1/dealer-kit`.
 * ---------------------------------------------------------------------------
 *
 * GET    /editions?pageId=            -> Edition[], newest first
 * GET    /editions/{id}               -> Edition
 * POST   /editions {pageId, name}     -> 201 Edition, 409 if one is already open
 * POST   /editions/{id}/submit        -> Edition   (page.edit)
 * POST   /editions/{id}/approve       -> Edition   (edition.approve)
 * POST   /editions/{id}/reject {reason} -> Edition (edition.approve)
 * POST   /editions/{id}/reopen        -> Edition   (page.edit)
 * POST   /editions/{id}/publish       -> Edition   (page.publish)
 *
 * **Three rights, and they are deliberately not the same one.** `page.edit`
 * starts and submits, `edition.approve` decides, `page.publish` moves the
 * published label. A Designer therefore gets a 403 on approve INCLUDING on
 * their own Edition (AC-L3), which is the whole point of the workflow.
 *
 * **Approving publishes nothing.** It records that a human read the catalogue
 * and WHICH version they read. Marking it done is what readers see (AC-L7).
 *
 * **`status` is the graph's key, never a status id.** The label travels beside
 * it so no screen keeps its own copy of the vocabulary.
 */

import { apiFetch } from '@/lib/api';
import { extractApiError } from '@/lib/api-client';

const BASE = '/api/v1/dealer-kit/editions';

/** The five states of the seeded `dealer_kit_edition` graph. */
export type EditionStatus =
  | 'draft'
  | 'pending_approval'
  | 'approved'
  | 'rejected'
  | 'done';

export interface Edition {
  id: string;
  pageId: string;
  /** The catalogue's name. Shown instead of the page id, which is a uuid. */
  pageName: string | null;
  name: string;
  status: EditionStatus;
  statusLabel: string;
  approvedVersionId: string | null;
  doneVersionId: string | null;
  previousEditionId: string | null;
  submittedAt: string | null;
  approvedAt: string | null;
  rejectionReason: string | null;
  createdAt: string;
}

function toEdition(wire: Partial<Edition>): Edition {
  return {
    id: String(wire.id ?? ''),
    pageId: String(wire.pageId ?? ''),
    pageName: wire.pageName ?? null,
    name: wire.name ?? 'Untitled edition',
    status: (wire.status as EditionStatus) ?? 'draft',
    statusLabel: wire.statusLabel ?? 'Draft',
    approvedVersionId: wire.approvedVersionId ?? null,
    doneVersionId: wire.doneVersionId ?? null,
    previousEditionId: wire.previousEditionId ?? null,
    submittedAt: wire.submittedAt ?? null,
    approvedAt: wire.approvedAt ?? null,
    rejectionReason: wire.rejectionReason ?? null,
    createdAt: wire.createdAt ?? '',
  };
}

export async function listEditions(pageId?: string): Promise<Edition[]> {
  const path = pageId ? `${BASE}?pageId=${encodeURIComponent(pageId)}` : BASE;
  const response = await apiFetch(path);
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Could not load editions'));
  }
  const rows = (await response.json()) as Partial<Edition>[];
  return (Array.isArray(rows) ? rows : []).map(toEdition);
}

export async function getEdition(editionId: string): Promise<Edition> {
  const response = await apiFetch(`${BASE}/${editionId}`);
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Could not load this edition'));
  }
  return toEdition(await response.json());
}

export async function createEdition(input: {
  pageId: string;
  name: string;
  previousEditionId?: string;
}): Promise<Edition> {
  const response = await apiFetch(BASE, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(input),
  });
  if (!response.ok) {
    // The 409 body already says what to do about it ("finish or reject the one
    // in progress"), so it is passed through rather than replaced.
    throw new Error(await extractApiError(response, 'Could not start this edition'));
  }
  return toEdition(await response.json());
}

/** Every transition is a POST to a named action. One helper, one contract. */
async function act(
  editionId: string,
  action: 'submit' | 'approve' | 'reject' | 'reopen' | 'publish',
  body?: Record<string, unknown>,
): Promise<Edition> {
  const response = await apiFetch(`${BASE}/${editionId}/${action}`, {
    method: 'POST',
    ...(body
      ? { headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }
      : {}),
  });
  if (!response.ok) {
    throw new Error(await extractApiError(response, `Could not ${action} this edition`));
  }
  return toEdition(await response.json());
}

export const submitEdition = (id: string) => act(id, 'submit');
export const approveEdition = (id: string) => act(id, 'approve');
export const rejectEdition = (id: string, reason: string) =>
  act(id, 'reject', { reason });
export const reopenEdition = (id: string) => act(id, 'reopen');
export const publishEdition = (id: string) => act(id, 'publish');
