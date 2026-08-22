/**
 * The office side of the revision fence (UAC `portal-submission-revisions`, C-bis).
 *
 * The backend mounts `require_current_revision(...)` on every office write that
 * mutates a revisable form: 34 routes across stock inquiry, purchase request /
 * sponsorship form and complaint. It reads `X-Revision-No`, compares it to the
 * row's current `revision_no`, and refuses a stale write with 409 plus one plain
 * sentence.
 *
 * It is 34 routes and not "everything under a record": the chat send, the view
 * link, the PDF export and the assignee sync are all deliberately left open, so
 * this file mirrors the fenced set rather than inferring it (`FENCED_COLLECTIONS`).
 *
 * **An absent header means unfenced, by design** - that is what keeps n8n, the
 * MCP server and the external API working, none of which knows what a revision
 * is. So a fence nobody sends the header to protects nothing: the office UI is
 * the one surface the fence exists for, and it is the one surface that has to
 * send it.
 *
 * ## Why this lives under `apiFetch` and not in the 34 call sites
 *
 * Sending the header is a property of the REQUEST URL, not of any one feature.
 * Threading a `revisionNo` argument through 34 service functions, their hooks
 * and their components would be 34 chances to forget one, and every new fenced
 * route would silently start out unfenced. `apiFetch` is the single choke point
 * every one of those writes already passes through, and it already carries an
 * interceptor of exactly this shape (`_attachImpersonationHeader`). So:
 *
 * * **Capture** - a GET of a fenced list or detail harvests `{id, revision_no}`
 *   off the response into a module-level registry. That is literally "the
 *   revision the user was looking at": it is the number the screen rendered.
 *   Capturing from the list too means a row action taken without ever opening
 *   the detail page is fenced as well.
 * * **Send** - a non-GET to one of the routes the backend actually fences (see
 *   `FENCED_COLLECTIONS`, an allowlist rather than "anything under a record")
 *   carries the remembered revision. Nothing remembered -> no header -> unfenced,
 *   which is the honest answer when we genuinely do not know what was on screen.
 * * **Refuse** - a 409 on a request WE fenced is normalized so the server's
 *   sentence reaches the caller whichever way it reads the body, and the record
 *   is refreshed so the user lands on the new revision instead of staring at the
 *   superseded one behind a toast.
 *
 * The registry keeps the HIGHEST revision seen per id. `revision_no` only ever
 * increments, so a stale list response arriving after a fresh detail response
 * cannot walk the number backwards and manufacture a 409.
 */

import { extractApiError } from '@/lib/api-client';

/** The header the backend's `revision_fence.py` reads. Same spelling, one place. */
export const REVISION_HEADER = 'X-Revision-No';

const UUID_PATTERN =
  '[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}';

/**
 * The fenced routes, one entry per fenced router, mirroring `_TARGETS` plus the
 * `require_current_revision(...)` mount sites in `app/services/revision_fence.py`
 * and the three routers that use it.
 *
 * `writes` is an ALLOWLIST of the sub-paths under `{root}/{id}` that the backend
 * actually fences (`''` being the record itself, i.e. `PUT`/`DELETE` on it). It is
 * not "every non-GET under a fenced record": the backend deliberately leaves
 * `/conversation/send-message` unfenced so a contact can still be messaged about a
 * revised record (AC O2), and `/view-link`, `/export/pdf`, `/sync-assignee` and
 * the manual template send are unfenced too. Stamping the header there is not
 * merely noise - it makes ANY 409 from those routes read as a revision conflict
 * and trigger a blanket cache invalidation for a conflict that has nothing to do
 * with revisions.
 *
 * An allowlist also fails safe the same way the backend does: a route added
 * upstream starts out unsent, and an absent header means unfenced, which is the
 * honest answer until this list learns about it.
 *
 * Complaint is listed even though its `portal_revision_configs` row ships
 * disabled: the backend target exists, so when the checkbox is flipped the
 * frontend arms itself with no code change (UAC CB4). Until the payload carries
 * a `revision_no` nothing is remembered and no header is sent.
 */
export const FENCED_COLLECTIONS = [
  {
    root: '/api/v1/procurement/stock-inquiries',
    writes: [
      '',
      'attachments',
      'response-attachments',
      'update-and-reply',
      'submit-for-project-sales',
      'project-sales-approve',
      'project-sales-reject',
      'purchasing-reject',
      'reopen',
      'void',
    ],
  },
  {
    root: '/api/v1/procurement/purchase-requests',
    writes: [
      '',
      'attachments',
      'update-and-reply',
      'set-pending-approval',
      'reject-submitted',
      'approval-decision',
      'process',
      'close',
      'void',
      'send-approval-link',
    ],
  },
  {
    root: '/api/v1/complaints-management/complaints',
    writes: [
      '',
      'attachments',
      'response-attachments',
      'update-and-reply',
      'approve',
      'reject',
      'process',
      'close',
      'void',
      'notify-root-cause',
      'notify-resolution',
    ],
  },
] as const;

type CollectionMatcher = {
  /** GET of the collection itself: the list the row actions are taken from. */
  list: RegExp;
  /** GET of one record: the detail page. */
  detail: RegExp;
  /** Any path under one record: `[1]` is the entity id, `[2]` the sub-path. */
  record: RegExp;
  /** The sub-paths the backend fences. `''` is the record itself. */
  writes: Set<string>;
};

const MATCHERS: CollectionMatcher[] = FENCED_COLLECTIONS.map(({ root, writes }) => ({
  list: new RegExp(`^${root}$`),
  detail: new RegExp(`^${root}/(${UUID_PATTERN})$`),
  record: new RegExp(`^${root}/(${UUID_PATTERN})(?:/(.*))?$`),
  writes: new Set<string>(writes),
}));

/**
 * The `/api/v1/...` path of a request, query string stripped.
 *
 * `apiFetch` may hand us an absolute URL (local dev points at :8000) or a
 * relative one (production goes through nginx), so match from `/api/v1/`
 * onwards rather than parsing an origin that may not be there.
 */
function apiPath(url: unknown): string | null {
  if (typeof url !== 'string') return null;
  const at = url.indexOf('/api/v1/');
  if (at < 0) return null;
  const path = url.slice(at);
  const cut = path.search(/[?#]/);
  return cut < 0 ? path : path.slice(0, cut);
}

/** True when this request is a GET whose body carries revisions worth keeping. */
export function isFencedReadPath(url: unknown, method?: string): boolean {
  if ((method ?? 'GET').toUpperCase() !== 'GET') return false;
  const path = apiPath(url);
  if (!path) return false;
  return MATCHERS.some((m) => m.list.test(path) || m.detail.test(path));
}

/**
 * The entity id a write is aimed at, when the URL is a route the backend fences.
 *
 * A sub-path the backend leaves unfenced returns null even though it sits under a
 * fenced record: no header goes out, and a 409 from it is left alone rather than
 * reported to the user as someone else's revision.
 */
export function fencedWriteEntityId(url: unknown, method?: string): string | null {
  const verb = (method ?? 'GET').toUpperCase();
  if (verb === 'GET' || verb === 'HEAD' || verb === 'OPTIONS') return null;
  const path = apiPath(url);
  if (!path) return null;
  for (const m of MATCHERS) {
    const hit = m.record.exec(path);
    if (!hit) continue;
    return m.writes.has(hit[2] ?? '') ? hit[1] : null;
  }
  return null;
}

// ---------------------------------------------------------------------------
// The registry: what revision each record was showing when we last read it.
// ---------------------------------------------------------------------------

const _seen = new Map<string, number>();

/** Remember one record's revision. Monotonic: never walks a number backwards. */
export function rememberRevision(id: unknown, revisionNo: unknown): void {
  if (typeof id !== 'string' || !id) return;
  // `Number(null)` is 0, and a payload with no `revision_no` at all - a type
  // whose column has not shipped yet - must read as UNKNOWN, not as revision 0.
  // Remembering 0 there would start sending a header for a record we never saw
  // a revision for.
  if (typeof revisionNo !== 'number' && typeof revisionNo !== 'string') return;
  if (typeof revisionNo === 'string' && !revisionNo.trim()) return;
  const next = Number(revisionNo);
  if (!Number.isFinite(next) || next < 0) return;
  const current = _seen.get(id);
  if (current !== undefined && current >= next) return;
  _seen.set(id, Math.trunc(next));
}

/** The revision we last saw for a record, or null when we never read it. */
export function rememberedRevision(id: string): number | null {
  const found = _seen.get(id);
  return found === undefined ? null : found;
}

/** Drop everything. Called on sign-out, and by tests between cases. */
export function clearRememberedRevisions(): void {
  _seen.clear();
}

/**
 * Harvest `{id, revision_no}` out of a fenced GET payload.
 *
 * Deliberately shallow: one record, or one page of them under `items` / `data`.
 * A deep walk would also swallow the revision TIMELINE payload, whose rows carry
 * a `revision_no` beside the revision row's own id, and poison the registry with
 * ids that are not entity ids.
 */
export function harvestRevisions(payload: unknown): void {
  if (!payload || typeof payload !== 'object') return;
  if (Array.isArray(payload)) {
    for (const row of payload) harvestRevisions(row);
    return;
  }
  const record = payload as Record<string, unknown>;
  const rows = record.items ?? record.data;
  if (Array.isArray(rows)) {
    for (const row of rows) {
      if (row && typeof row === 'object') {
        const entry = row as Record<string, unknown>;
        rememberRevision(entry.id, entry.revision_no);
      }
    }
    return;
  }
  rememberRevision(record.id, record.revision_no);
}

// ---------------------------------------------------------------------------
// Refusal handling: refresh the record, do not leave the user on a dead version.
// ---------------------------------------------------------------------------

type StaleHandler = (entityId: string) => void;

let _onStale: StaleHandler | null = null;

/**
 * Register what to do when the server refuses a write as stale.
 *
 * Wired once in `providers/query-provider.tsx` to invalidate the react-query
 * cache, which is what actually puts the new revision on screen. Kept as a
 * registration rather than importing a query client here so this module stays
 * free of React and usable from `lib/api.ts` on either side of the boundary.
 */
export function registerRevisionStaleHandler(handler: StaleHandler | null): void {
  _onStale = handler;
}

/**
 * Turn a fenced 409 into a refresh plus a response every caller reads correctly.
 *
 * The services in this repo read an error body three different ways
 * (`err.detail`, `err.message`, `extractApiError`). The server sends only
 * `detail`, so the two hand-rolled readers would have thrown `Error(undefined)`
 * and toasted nothing on exactly the conflict this feature exists to report.
 * Extract the sentence ONCE, here, with `extractApiError`, and hand back a 409
 * carrying it under both keys - so the sentence reaches the user through the
 * error path each call site already has, with no per-call-site change and no
 * second toast competing with the first.
 */
export async function handleRevisionConflict(
  entityId: string,
  response: Response,
): Promise<Response> {
  const message = await extractApiError(
    response.clone(),
    'This record was revised while you were working on it. Reload to see the latest revision.',
  );
  try {
    _onStale?.(entityId);
  } catch {
    /* a failed refresh must never swallow the refusal itself */
  }
  return new Response(JSON.stringify({ detail: message, message }), {
    status: 409,
    statusText: response.statusText,
    headers: { 'Content-Type': 'application/json' },
  });
}
