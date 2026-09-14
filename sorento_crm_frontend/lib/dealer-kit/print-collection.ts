/**
 * Who prints a price tag request, and what happens after it is approved
 * (r9 S3/D7-D11).
 *
 * A request used to end at "ready", which said nothing about whether anybody
 * had the tags in their hands. It now says who prints: the salesperson prints
 * their own copy and the request is finished at `approved`, or the office
 * prints and there is a hand-over to record - `ready_for_collection`, then
 * `collected` (by hand, or automatically after the configured days).
 *
 * ## Expected API contract (Phase 1: the overrides below stand in)
 *
 * ```
 * price_tag_requests.print_by  "office" | "self" | null
 *
 * POST /api/v1/public/portal/submissions/price_tag_request        (create)
 * PUT  /api/v1/public/portal/submissions/price_tag_request/{id}   (update)
 *   { ..., print_by: "office" | "self" | null }
 * POST .../submit
 *   422 { code: "PRINT_BY_REQUIRED" } while print_by is null
 *
 * GET  any read of the request now carries:
 *   print_by, ready_for_collection_at, collected_at, collected_auto,
 *   collected_by_name
 *
 * PATCH /api/v1/dealer-kit/price-tag-requests/{id}
 *   { print_by }                     the office fixing the choice, not terminal
 *
 * POST /api/v1/dealer-kit/price-tag-requests/{id}/transition
 *   { status: "ready_for_collection" }   only from approved AND print_by=office
 *   { status: "collected" }              only from ready_for_collection
 *
 * POST /api/v1/public/portal/submissions/price_tag_request/{id}/collect
 *   200 { status: "collected" }      the salesperson confirming the hand-over
 *
 * GET/PUT /api/v1/user-management/settings(/general)
 *   price_tag_auto_collect_days INT 0..90, default 7, 0 = off
 * ```
 *
 * `ready` is retired: every row that carried it becomes `approved` in the
 * migration, and nothing in the UI offers it again.
 */

export type PrintBy = 'office' | 'self';

export const PRINT_BY_OPTIONS: { value: PrintBy; label: string }[] = [
  { value: 'office', label: 'Office prints' },
  { value: 'self', label: 'I print myself' },
];

/** What a reader sees, including the rows that predate the choice. */
export function printByLabel(value?: PrintBy | string | null): string {
  const found = PRINT_BY_OPTIONS.find((option) => option.value === value);
  return found ? found.label : 'Not set';
}

/**
 * Nothing left to do (D8).
 *
 * Request-aware, because `approved` is the end of the line for a salesperson
 * who prints their own tags and the middle of it for an office print.
 */
export function isTerminalPriceTagStatus(
  status?: string | null,
  printBy?: PrintBy | string | null,
): boolean {
  const current = (status ?? '').trim().toLowerCase();
  if (['collected', 'rejected', 'void'].includes(current)) return true;
  return current === 'approved' && printBy === 'self';
}

/** When an untouched hand-over closes itself, or null when the sweep is off. */
export function autoCollectOn(
  readyAt?: string | null,
  days?: number | null,
): Date | null {
  if (!readyAt || !days || days <= 0) return null;
  const from = new Date(readyAt);
  if (Number.isNaN(from.getTime())) return null;
  return new Date(from.getTime() + days * 24 * 60 * 60 * 1000);
}

/** The bounds the setting accepts. 0 turns the sweep off entirely. */
export const AUTO_COLLECT_DAYS_MIN = 0;
export const AUTO_COLLECT_DAYS_MAX = 90;
export const AUTO_COLLECT_DAYS_DEFAULT = 7;

// ---------------------------------------------------------------------------
// PHASE 1 MOCK - deleted when the column, the routes and the setting exist
// ---------------------------------------------------------------------------

/**
 * What the backend does not carry yet, remembered per request in this tab.
 *
 * Two jobs, both temporary. First, a `print_by` the server drops on save would
 * otherwise vanish on the next read, so the choice could not be walked at all.
 * Second, the collection statuses do not exist in the status graph yet, so a
 * real transition would 409: this lets the CRM and the portal be walked at
 * `approved` + office and at `ready_for_collection` without pushing a shared
 * dev row through a graph that cannot take it back.
 */
export interface PriceTagCollectionOverride {
  print_by?: PrintBy | null;
  status?: string;
  ready_for_collection_at?: string | null;
  collected_at?: string | null;
  collected_by_name?: string | null;
  collected_auto?: boolean;
}

const overrides = new Map<string, PriceTagCollectionOverride>();

let autoCollectDays: number | null = null;

/** Merge whatever this tab knows over a fetched request. */
export function applyCollectionOverride<T extends { id: string }>(request: T): T {
  const override = overrides.get(request.id);
  return override ? { ...request, ...override } : request;
}

export function setCollectionOverride(
  requestId: string,
  patch: PriceTagCollectionOverride,
): void {
  overrides.set(requestId, { ...(overrides.get(requestId) ?? {}), ...patch });
}

export function readAutoCollectDaysOverride(): number | null {
  return autoCollectDays;
}

export function setAutoCollectDaysOverride(days: number): void {
  autoCollectDays = days;
}

export function _resetCollectionOverrides(): void {
  overrides.clear();
  autoCollectDays = null;
}

/**
 * The overrides on `window`, for a Phase 1 browser walk: the statuses the
 * graph cannot reach yet have to be seen somehow. Goes away with the store.
 */
if (typeof window !== 'undefined') {
  (window as unknown as Record<string, unknown>).__ptagPrintMock = {
    set: setCollectionOverride,
    days: setAutoCollectDaysOverride,
    reset: _resetCollectionOverrides,
  };
}
