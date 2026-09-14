/**
 * CRM-side price tag request service.
 *
 * Calls `/api/v1/dealer-kit/price-tag-requests` via `apiFetch`.
 *
 * ===========================================================================
 * ONE LINE, MANY TAGS (PLAN-price-tag-combos.md D3, slice S3)
 * ===========================================================================
 * A request LINE is what the salesperson asked for. A TAG is what gets
 * printed. They were the same thing until S3; now a line whose package leaves
 * a choice group open is split by marketing into one tag per candidate, each
 * with its own design, quantity, choices and marketing override. A tag is
 * shown as "1a", "1b" (line index plus a letter) and never as an id (AC-X-2).
 *
 * ---- BACKEND CONTRACT (S3 Phase 2 builds this; the mock block at the bottom
 *      of this file stands in until then) --------------------------------
 *
 *  GET /dealer-kit/price-tag-requests/{id}
 *    `lines[]` gains:
 *      `parts: PriceTagRequestLinePart[]`   what the salesperson asked for (S2)
 *      `package_warning: string | null`     the S2 guard's verdict
 *      `tags: PriceTagRequestTag[]`         one per printed tag, sort order
 *    and LOSES `marketing_price_override` / `marketing_override_reason`, which
 *    move onto the tag, and `alternatives`, which is dropped in S2.
 *
 *  POST /dealer-kit/price-tag-requests/{id}/resolve-prices
 *    body: string[] | null  (TAG ids now, or null for every tag)
 *    -> one row per TAG: today's keys plus `tag_id`, `line_id`, `tag_label`,
 *       `open_groups` and `parts`; `quantity` is the TAG's.
 *
 *  PATCH /dealer-kit/price-tag-requests/{id}/tags/{tag_id}
 *    body `{quantity?, marketing_price_override?, marketing_override_reason?,
 *    choices?}` -> the updated tag. "Pick one" sends `choices`; the marketing
 *    override moves here from the retired line route.
 *
 *  POST /dealer-kit/price-tag-requests/{id}/tags/{tag_id}/split
 *    body `{role}` -> the LINE's tags after the split. The tag keeps its id,
 *    its geometry and its pins and resolves to candidate 1; N-1 siblings are
 *    inserted after it, one per remaining candidate, with the geometry copied
 *    in the draft doc.
 *
 *  DELETE /dealer-kit/price-tag-requests/{id}/tags/{tag_id}
 *    204, or 422 `LAST_TAG` when it is the line's only tag. No UI in S3 (the
 *    UAC puts tag removal on the designer in a later round); documented because
 *    it is part of D3's route table.
 *
 *  PUT /dealer-kit/price-tag-requests/{id}/lines/{line_id}   REMOVED
 *    `updateRequestLine` is gone with it: the override it carried is a tag fact.
 *
 *  The tag sheet document keys its placements by `request_tag_id` (see
 *  `PlacedTag`), and the print payload's `resolvedData` is keyed the same way.
 *  The S3 migration rewrites every saved doc.
 * ===========================================================================
 */

import { apiFetch } from '@/lib/api';
import { buildDataGridParams, extractApiError } from '@/lib/api-client';
import type { LineTagData, TagSheetDoc } from '@/lib/dealer-kit/tag-template-types';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export type PriceTagLineType = 'product' | 'product_set';

/** One part under a line: what the salesperson asked to come with it (S2, D2). */
export interface PriceTagRequestLinePart {
  id: string;
  product_id: string | null;
  code: string | null;
  name: string | null;
  /** The choice group this row answers. Null on a fixed or hand-added part. */
  role: string | null;
  /** The group's options, on a row still open. Codes, never ids (AC-X-2). */
  candidates: { product_id: string; code: string; name: string }[];
  sort_order: number;
}

/**
 * One printed tag under a line (D3).
 *
 * `choices` is the stored `{role: product_id}` map and is never rendered;
 * `choices_display` is the same answer resolved to codes, which is what the
 * rail and the Lines tab show (AC-X-2). `list_price` / `sell_price` ride along
 * because price is a TAG fact since D4 - the host plus this tag's own resolved
 * parts - and both surfaces the brief asks for render them per tag.
 */
export interface PriceTagRequestTag {
  id: string;
  sort_order: number;
  /** "1a", "1b" - line index plus a letter. Never an id. */
  label: string;
  quantity: number;
  choices: Record<string, string>;
  choices_display: { role: string; code: string }[];
  /** Groups still undecided on this tag: what Split / Pick one act on.
   *  Candidates carry the id beside the code - see `TagOpenGroup`. */
  open_groups: { role: string; candidates: { product_id: string; code: string }[] }[];
  marketing_price_override: number | null;
  marketing_override_reason: string | null;
  list_price: number | null;
  sell_price: number | null;
}

export interface PriceTagRequestLine {
  id: string;
  line_type: PriceTagLineType;
  product_id: string | null;
  product_set_id: string | null;
  name: string;
  code: string;
  show_promo_price: boolean;
  quantity: number;
  included_accessories: string | null;
  /** Free-text note on the line (D6). Optional: absent on a request created
   *  before r7. */
  remarks?: string | null;
  sort_order: number;
  /** Resolved list price. */
  list_price: number | null;
  /** Resolved selling price. */
  sell_price: number | null;
  /** The package under this line, in display order (S2). */
  parts: PriceTagRequestLinePart[];
  /** What the S2 package guard found at submit. Null = clean. */
  package_warning: string | null;
  /** What gets printed for this line: one tag by default, N after a split. */
  tags: PriceTagRequestTag[];
}

/** Header-level price mode (D5): replaces the per-line "Promo price" switch. */
export type PriceMode = 'list' | 'selling';

/**
 * The shape `entity_attachment_service.list_attachments_for_entity` answers
 * with - the SAME shape the portal's own detail route carries (D49, S1), so
 * this and the portal's `PortalAttachment` type must never drift apart again.
 * No `id` field: `link_id` is the row identity (what a key/unlink target
 * reads), `attachment_id` is what the download route is keyed on - the two
 * are NOT interchangeable.
 */
export interface PriceTagAttachment {
  link_id: string;
  attachment_id: string;
  filename: string | null;
  size: number | null;
  url: string | null;
  content_type: string | null;
  uploaded_at: string | null;
  uploader_kind: 'user' | 'contact' | 'system' | null;
  uploaded_by_name: string | null;
  uploaded_by_role: 'contact' | 'staff' | 'unknown';
  can_unlink: boolean;
}

export interface PriceTagRequestSummary {
  id: string;
  doc_number: string;
  debtor_code: string | null;
  /** Null while the portal request is still a draft (D48a). */
  debtor_name: string | null;
  promotion_id: string | null;
  promotion_name: string | null;
  needed_by_date: string | null;
  notes: string | null;
  /** Defaults to 'list' server-side; absent on a request created before r7. */
  price_mode?: PriceMode;
  status: string;
  line_count: number;
  created_at: string;
  assigned_to_id: string | null;
  assigned_to_name: string | null;
  contact_name: string | null;
}

export interface PriceTagRequestDetail extends PriceTagRequestSummary {
  contact_id: string;
  lines: PriceTagRequestLine[];
  attachments?: PriceTagAttachment[];
  /** Whether a completed (READY) tag sheet PDF export exists (S10 Proof tab). */
  has_completed_export?: boolean;
}

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const BASE = '/api/v1/dealer-kit/price-tag-requests';

// ---------------------------------------------------------------------------
// API surface
// ---------------------------------------------------------------------------

export interface PriceTagRequestListParams {
  page: number;
  limit: number;
  sort?: string;
  dir?: 'asc' | 'desc';
  query?: string;
  status?: string;
}

export interface PriceTagRequestListResult {
  data: PriceTagRequestSummary[];
  pagination: { total: number; page: number; limit: number };
}

export async function listPriceTagRequests(
  params: PriceTagRequestListParams,
): Promise<PriceTagRequestListResult> {
  // Through `buildDataGridParams`, which is the one place page/limit/sort/dir/
  // query are spelled. The list and the record pager both call this with the
  // page-number shape, so it is translated here rather than in two callers.
  const usp = buildDataGridParams(
    {
      pageIndex: params.page - 1,
      pageSize: params.limit,
      sorting: params.sort
        ? [{ id: params.sort, desc: params.dir === 'desc' }]
        : [],
      searchQuery: params.query ?? '',
    },
    { status: params.status },
  );

  const response = await apiFetch(`${BASE}?${usp.toString()}`);
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Failed to load price tag requests'));
  }

  // The page and the true total, both counted by the server. This used to fetch
  // the WHOLE table and sort and slice it here, so every keystroke shipped every
  // request in the system and the record count under the grid was the length of
  // the array that happened to arrive.
  const body: {
    data: PriceTagRequestSummary[];
    pagination: { total: number; page: number; limit: number };
  } = await response.json();

  return {
    data: body.data ?? [],
    pagination: {
      total: body.pagination?.total ?? 0,
      page: body.pagination?.page ?? params.page,
      limit: body.pagination?.limit ?? params.limit,
    },
  };
}

export async function getPriceTagRequest(
  id: string,
): Promise<PriceTagRequestDetail | null> {
  const response = await apiFetch(`${BASE}/${encodeURIComponent(id)}`);
  if (response.status === 404) return null;
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Failed to load price tag request'));
  }
  // PHASE 1: the backend answers today's line shape, so the package and the
  // tags are filled in by the mock. Phase 2 deletes the call and returns the
  // body straight, exactly as this did before.
  return mockDecorateRequest(await response.json());
}

export async function claimPriceTagRequest(
  id: string,
): Promise<PriceTagRequestDetail> {
  const response = await apiFetch(`${BASE}/${encodeURIComponent(id)}/claim`, {
    method: 'POST',
  });
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Failed to claim request'));
  }
  return response.json();
}

export async function transitionPriceTagRequest(
  id: string,
  action: string,
): Promise<PriceTagRequestDetail> {
  const response = await apiFetch(`${BASE}/${encodeURIComponent(id)}/transition`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ status: action }),
  });
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Failed to transition request'));
  }
  return response.json();
}

// ---------------------------------------------------------------------------
// Tag update, split and pick one (D3)
// ---------------------------------------------------------------------------

export interface PriceTagRequestTagUpdate {
  quantity?: number;
  marketing_price_override?: number | null;
  marketing_override_reason?: string | null;
  /** `{role: product_id}` - what "Pick one" writes. */
  choices?: Record<string, string>;
}

/** PATCH one tag. Replaces the retired line-level PUT. */
export async function updateRequestTag(
  requestId: string,
  tagId: string,
  data: PriceTagRequestTagUpdate,
): Promise<PriceTagRequestTag> {
  return mockUpdateTag(requestId, tagId, data);
}

/**
 * "Split into N tags": the tag resolves to the group's first candidate and
 * N-1 siblings follow it, one per remaining candidate. Answers the LINE's tags.
 */
export async function splitRequestTag(
  requestId: string,
  tagId: string,
  role: string,
): Promise<PriceTagRequestTag[]> {
  return mockSplitTag(requestId, tagId, role);
}

// ---------------------------------------------------------------------------
// Tag sheet design (S4)
// ---------------------------------------------------------------------------

export async function getTagSheetDoc(
  requestId: string,
): Promise<TagSheetDoc | null> {
  const response = await apiFetch(
    `${BASE}/${encodeURIComponent(requestId)}/design`,
  );
  if (response.status === 404) return null;
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Failed to load tag sheet design'));
  }
  // `source` says whether this is the autosaved draft or the last deliberate
  // save (B1). The designer opens on either identically - what it edits is the
  // document, not its provenance - so it is read past here rather than
  // returned; the field exists so the backend contract stays legible and a
  // future "unsaved changes" cue has something to read.
  const result: {
    page_id: string;
    version: number;
    doc: TagSheetDoc | null;
    source: 'draft' | 'version';
  } = await response.json();
  // PHASE 1: stands in for the S3 migration's step 2, which rewrites every
  // saved doc's `request_line_id` to the line's tag id. Without it a design
  // saved before this slice opens as though nothing had ever been drawn.
  return mockRekeyDoc(result.doc ?? null);
}

/**
 * Autosave: overwrite the request's tag sheet DRAFT. Writes no version (B1).
 *
 * `keepalive` is for the page-teardown flush only. The browser cancels a normal
 * fetch when the document goes away, which is exactly the moment the last edit
 * most needs to reach the server; `keepalive` lets it outlive the page. It is
 * NOT the default because a keepalive request body is capped at 64KB and a
 * busy tag sheet exceeds that - the fetch would reject outright, turning every
 * ordinary autosave on a large document into a failure.
 */
export async function saveTagSheetDraft(
  requestId: string,
  doc: TagSheetDoc,
  options: { keepalive?: boolean } = {},
): Promise<void> {
  const response = await apiFetch(
    `${BASE}/${encodeURIComponent(requestId)}/design/draft`,
    {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ doc }),
      keepalive: options.keepalive,
    },
  );
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Failed to save tag sheet design'));
  }
}

/** Manual Save: snapshot the design into a new immutable version (B1). */
export async function saveTagSheetDoc(
  requestId: string,
  doc: TagSheetDoc,
): Promise<void> {
  const response = await apiFetch(
    `${BASE}/${encodeURIComponent(requestId)}/design`,
    {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ doc }),
    },
  );
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Failed to save tag sheet design'));
  }
}

/**
 * Display data for this request's lines, resolved by the backend.
 *
 * ```
 * POST /api/v1/dealer-kit/price-tag-requests/{id}/resolve-prices
 *   body: string[] | null   line ids, or null for every line
 *   200 [{ line_id, code, name, dimensions, spec_lines, set_members, images[],
 *          list_price, sell_price, show_promo_price, included_accessories,
 *          quantity }]
 * ```
 *
 * Prices resolve at render time through the pricing engine and are never stored
 * in the tag sheet document (ADR 0008). A marketing override on the TAG wins
 * over the resolved offer, which is why this is resolved per tag rather than
 * per product.
 *
 * One row per TAG since S3 (D3) - see the contract at the top of this file.
 */
export async function resolveRequestTags(
  requestId: string,
  request: PriceTagRequestDetail,
  tagIds?: string[],
): Promise<LineTagData[]> {
  const response = await apiFetch(
    `${BASE}/${encodeURIComponent(requestId)}/resolve-prices`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      // PHASE 1: the backend still keys on LINES, so it is asked for all of
      // them and the per-tag rows are expanded below. Phase 2 sends `tagIds`.
      body: JSON.stringify(null),
    },
  );
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Failed to resolve line prices'));
  }
  const rows = (await response.json()) as LineTagData[];
  return mockExpandResolvedRows(rows, request, tagIds);
}

// ---------------------------------------------------------------------------
// Export (S5)
// ---------------------------------------------------------------------------

export interface ExportResult {
  downloadId: string;
  status: string;
  filename: string | null;
}

export async function exportTagSheet(
  requestId: string,
  sheetIds?: string[],
): Promise<ExportResult> {
  const response = await apiFetch(
    `${BASE}/${encodeURIComponent(requestId)}/export`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ sheet_ids: sheetIds ?? null }),
    },
  );
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Failed to export tag sheet'));
  }
  return response.json();
}

// ---------------------------------------------------------------------------
// --- mock --- PHASE 1 ONLY (DEBT, not done). Deleted in S3 Phase 2, when the
// backend answers tags of its own and each function above becomes the plain
// apiFetch its contract at the top of this file describes.
//
// Two things it has to get right for the designer to be exercisable:
//
//  * A tag id must be STABLE across calls and across reloads, because the saved
//    tag sheet document keys its placements on it. The base tag of a line
//    therefore IS the line id, which also means a document saved before S3
//    keeps working untouched in Phase 1.
//  * A request needs a line with an OPEN group, or Split and Pick one have
//    nothing to act on. The package is assigned by the same hash of the product
//    id the S2 portal mock uses, so the two halves of the lane tell the same
//    story about the same product.
// ---------------------------------------------------------------------------

/** Extra tags a split created, by line id. Lives as long as the tab. */
const mockSplitTags = new Map<string, { id: string; role: string; code: string }[]>();
/** What "Pick one" resolved, by tag id: `{role: code}`. */
const mockPicked = new Map<string, Record<string, string>>();
/** Per-tag marketing overrides, by tag id. */
const mockOverrides = new Map<
  string,
  { marketing_price_override: number | null; marketing_override_reason: string | null }
>();

const MOCK_BASIN_ROLE = 'Basin';
const MOCK_BASIN_CANDIDATES = [
  'SRTBS801-WH',
  'SRTBS801-BL',
  'SRTBS801-GY',
  'SRTBS801-MT',
];
const MOCK_FIXED_PARTS = [
  { code: 'SRTTT8050', name: 'Table top 800 x 500' },
  { code: 'SRTMR502', name: 'Mirror 500 x 700' },
];

function mockBucket(productId: string | null): number {
  if (!productId) return 0;
  let sum = 0;
  for (let i = 0; i < productId.length; i += 1) sum += productId.charCodeAt(i);
  return sum % 4;
}

/** "1a", "1b", ... "1z" then "1z1" - a label, never an id (AC-X-2). */
function mockTagLabel(lineIndex: number, tagIndex: number): string {
  const letter = String.fromCharCode(97 + (tagIndex % 26));
  const wrap = Math.floor(tagIndex / 26);
  return `${lineIndex + 1}${letter}${wrap > 0 ? wrap : ''}`;
}

function mockPartsFor(line: PriceTagRequestLine): PriceTagRequestLinePart[] {
  const bucket = mockBucket(line.product_id);
  if (line.line_type !== 'product' || bucket < 2) return [];
  const parts: PriceTagRequestLinePart[] = MOCK_FIXED_PARTS.map((part, index) => ({
    id: `${line.id}::p${index}`,
    product_id: `mock-part-${part.code}`,
    code: part.code,
    name: part.name,
    role: null,
    candidates: [],
    sort_order: index,
  }));
  parts.push({
    id: `${line.id}::open`,
    product_id: null,
    code: null,
    name: null,
    role: MOCK_BASIN_ROLE,
    candidates: MOCK_BASIN_CANDIDATES.map((code) => ({
      product_id: `mock-part-${code}`,
      code,
      name: `Basin 800 ${code.slice(-2)}`,
    })),
    sort_order: parts.length,
  });
  return parts;
}

function mockWarningFor(line: PriceTagRequestLine): string | null {
  // Bucket 1 is the guarded product with no package at all - the S2 warning
  // marketing is meant to see on this page.
  return line.line_type === 'product' && mockBucket(line.product_id) === 1
    ? 'No package defined'
    : null;
}

function mockTagsFor(
  line: PriceTagRequestLine,
  lineIndex: number,
  parts: PriceTagRequestLinePart[],
): PriceTagRequestTag[] {
  const openPart = parts.find((part) => part.product_id === null && part.role);
  const siblings = mockSplitTags.get(line.id) ?? [];
  const rows: { id: string; forcedCode?: string }[] = [
    { id: line.id },
    ...siblings.map((sibling) => ({ id: sibling.id, forcedCode: sibling.code })),
  ];

  return rows.map((row, index) => {
    const picked = mockPicked.get(row.id) ?? {};
    const resolvedCode = row.forcedCode ?? picked[openPart?.role ?? ''] ?? null;
    const override = mockOverrides.get(row.id);
    const choicesDisplay =
      openPart && resolvedCode ? [{ role: openPart.role as string, code: resolvedCode }] : [];
    return {
      id: row.id,
      sort_order: index,
      label: mockTagLabel(lineIndex, index),
      quantity: line.quantity,
      // The stored shape is `{role: product_id}`; the mock's part ids are
      // derived from the code, which is why both can be answered from one map.
      choices: Object.fromEntries(
        choicesDisplay.map((choice) => [choice.role, `mock-part-${choice.code}`]),
      ),
      choices_display: choicesDisplay,
      open_groups:
        openPart && !resolvedCode
          ? [
              {
                role: openPart.role as string,
                candidates: MOCK_BASIN_CANDIDATES.map((code) => ({
                  product_id: `mock-part-${code}`,
                  code,
                })),
              },
            ]
          : [],
      marketing_price_override: override?.marketing_price_override ?? null,
      marketing_override_reason: override?.marketing_override_reason ?? null,
      list_price: line.list_price,
      sell_price: line.sell_price,
    };
  });
}

function mockDecorateRequest(detail: PriceTagRequestDetail): PriceTagRequestDetail {
  return {
    ...detail,
    lines: (detail.lines ?? []).map((line, index) => {
      const parts = line.parts?.length ? line.parts : mockPartsFor(line);
      return {
        ...line,
        parts,
        package_warning: line.package_warning ?? mockWarningFor(line),
        tags: mockTagsFor(line, index, parts),
      };
    }),
  };
}

/** One resolver row per tag, off the per-line rows the backend still answers. */
function mockExpandResolvedRows(
  rows: LineTagData[],
  request: PriceTagRequestDetail,
  tagIds?: string[],
): LineTagData[] {
  const byLine = new Map(rows.map((row) => [row.line_id, row]));
  const wanted = tagIds ? new Set(tagIds) : null;
  const out: LineTagData[] = [];
  for (const line of request.lines) {
    const row = byLine.get(line.id);
    if (!row) continue;
    for (const tag of line.tags) {
      if (wanted && !wanted.has(tag.id)) continue;
      const parts = line.parts
        .filter((part) => part.product_id !== null)
        .map((part) => ({
          code: part.code ?? '',
          name: part.name ?? '',
          dimensions: '',
        }));
      for (const choice of tag.choices_display) {
        parts.push({ code: choice.code, name: `Basin 800 ${choice.code.slice(-2)}`, dimensions: '' });
      }
      out.push({
        ...row,
        tag_id: tag.id,
        line_id: line.id,
        tag_label: tag.label,
        open_groups: tag.open_groups,
        parts,
        quantity: tag.quantity,
      });
    }
  }
  return out;
}

async function mockUpdateTag(
  _requestId: string,
  tagId: string,
  data: PriceTagRequestTagUpdate,
): Promise<PriceTagRequestTag> {
  await new Promise((resolve) => setTimeout(resolve, 150));
  if (data.choices) {
    // The real route stores product ids; the mock's ids carry the code, so the
    // display value is read back out of them rather than looked up again.
    const asCodes: Record<string, string> = {};
    for (const [role, productId] of Object.entries(data.choices)) {
      asCodes[role] = productId.replace(/^mock-part-/, '');
    }
    mockPicked.set(tagId, { ...(mockPicked.get(tagId) ?? {}), ...asCodes });
  }
  if ('marketing_price_override' in data || 'marketing_override_reason' in data) {
    const existing = mockOverrides.get(tagId);
    mockOverrides.set(tagId, {
      marketing_price_override:
        data.marketing_price_override ?? existing?.marketing_price_override ?? null,
      marketing_override_reason:
        data.marketing_override_reason ?? existing?.marketing_override_reason ?? null,
    });
  }
  return {
    id: tagId,
    sort_order: 0,
    label: '',
    quantity: data.quantity ?? 1,
    choices: data.choices ?? {},
    choices_display: [],
    open_groups: [],
    marketing_price_override: mockOverrides.get(tagId)?.marketing_price_override ?? null,
    marketing_override_reason: mockOverrides.get(tagId)?.marketing_override_reason ?? null,
    list_price: null,
    sell_price: null,
  };
}

async function mockSplitTag(
  _requestId: string,
  tagId: string,
  role: string,
): Promise<PriceTagRequestTag[]> {
  await new Promise((resolve) => setTimeout(resolve, 200));
  // The tag being split is the line's base tag, whose id IS the line id.
  const lineId = tagId;
  mockPicked.set(lineId, { [role]: MOCK_BASIN_CANDIDATES[0] });
  mockSplitTags.set(
    lineId,
    MOCK_BASIN_CANDIDATES.slice(1).map((code, index) => ({
      id: `${lineId}::s${index + 1}`,
      role,
      code,
    })),
  );
  return [];
}

/**
 * A saved doc read through the S3 key rename.
 *
 * The mock's base tag id IS the line id (see the note at the top of this
 * block), so the rewrite the migration does once is a straight rename here.
 * A doc already carrying `request_tag_id` passes through untouched.
 */
function mockRekeyDoc(doc: TagSheetDoc | null): TagSheetDoc | null {
  if (!doc) return doc;
  let changed = false;
  const sheets = doc.sheets.map((sheet) => ({
    ...sheet,
    tags: sheet.tags.map((tag) => {
      if (tag.request_tag_id) return tag;
      const legacy = (tag as unknown as { request_line_id?: string }).request_line_id;
      if (!legacy) return tag;
      changed = true;
      return { ...tag, request_tag_id: legacy };
    }),
  }));
  return changed ? { ...doc, sheets } : doc;
}
