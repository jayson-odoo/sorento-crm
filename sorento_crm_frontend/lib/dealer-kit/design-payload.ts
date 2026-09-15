/**
 * The tag sheet design payload both design surfaces read (r9 S1/D1).
 *
 * ## Why one shape
 *
 * The PDF print page already receives everything a sheet needs to draw itself:
 * the document, the resolved line data, and the three media maps - `assets`
 * (library artwork by asset id), `images` (product photos by attachment id) and
 * `fonts` (brand faces). The portal preview and the CRM detail preview drew the
 * same document WITHOUT those maps, so every image layer painted a grey box and
 * every brand face fell back to a system sans. One shape, three callers, so the
 * proof, the preview and the print can never disagree again.
 *
 * ## Expected API contract (Phase 1: FE-first, backend catches up in Phase 2)
 *
 * Portal (salesperson, token auth), status-gated to the statuses at which a
 * design is visible - `proof_ready | changes_requested | approved |
 * ready_for_collection | collected` after S3 retires `ready`:
 *
 * ```
 * GET /api/v1/public/portal/submissions/price_tag_request/{id}/design
 *   200 {
 *     page_id: string,
 *     version: number,
 *     source: "draft" | "version",     // portal always "version" (prefer="version")
 *     doc: TagSheetDoc | null,
 *     lines: LineTagData[],            // resolved at read time (ADR 0008)
 *     assets: { [assetId: string]: string },        // signed URL per library asset
 *     images: { [attachmentId: string]: string },   // signed URL per product photo
 *     fonts: { name: string, family: string, url: string }[]
 *   }
 *   404 while no design exists, or the status does not expose one yet.
 * ```
 *
 * CRM (marketing, JWT), draft-first so the designer's autosave is what the
 * detail page shows, and visible from `designing`:
 *
 * ```
 * GET /api/v1/dealer-kit/price-tag-requests/{id}/design
 *   200 same body as above, with source "draft" | "version"
 *   404 while the request has no page yet.
 * ```
 *
 * Both bodies are the print payload (`resolve_tag_sheet_print_payload`) minus
 * its download-scoped fields, which is deliberate: one backend resolver, three
 * readers.
 *
 * Until the backend carries the three media keys, the service layer normalises
 * what is missing (see `designPayloadFromResponse`) - `images` is derivable
 * from the lines the response already carries, `assets` and `fonts` are not, so
 * artwork and brand faces stay blank rather than wrong.
 */

import type {
  LineTagData,
  TagSheetDoc,
} from '@/lib/dealer-kit/tag-template-types';
import type { TagFont } from '@/lib/dealer-kit/fonts';
import type { ResolvedLineData } from '@/app/(public)/c/print/tag-sheet/[downloadId]/components/TagSheetRenderer';

export interface TagSheetDesignPayload {
  page_id: string;
  version: number;
  source: 'draft' | 'version';
  doc: TagSheetDoc | null;
  /** Line id -> everything that line's tag draws. */
  resolvedData: Record<string, ResolvedLineData>;
  /** assetId -> signed URL, for every library asset the document names. */
  assets: Record<string, string>;
  /** attachmentId -> signed URL, for the bound products' own photos. */
  images: Record<string, string>;
  /** Brand fonts, loaded through `ensureFontsLoaded` before the sheet draws. */
  fonts: TagFont[];
}

/** The raw body either endpoint answers with. */
export interface TagSheetDesignResponse {
  page_id?: string;
  version?: number;
  source?: 'draft' | 'version';
  doc: TagSheetDoc | null;
  lines?: LineTagData[];
  assets?: Record<string, string> | null;
  images?: Record<string, string> | null;
  fonts?: TagFont[] | null;
}

/**
 * Response -> payload, with the media maps normalised.
 *
 * `images` is rebuilt from the lines when the body omits the map: every line
 * already carries its photos WITH their signed URLs, so a product photo slot
 * can draw today without waiting for the backend half. `assets` and `fonts`
 * have no such fallback - an image layer with no URL keeps its blank box, which
 * is what it does now.
 */
export function designPayloadFromResponse(
  body: TagSheetDesignResponse,
): TagSheetDesignPayload {
  const lines = body.lines ?? [];
  const resolvedData: Record<string, ResolvedLineData> = {};
  // Keyed by the TAG, not the line: since the combos model, one line can
  // carry more than one placed tag (`request_tag_id`), and `TagSheetRenderer`
  // reads this map by that id. Keying it by `line_id` instead answered every
  // sheet with the first tag's data on every OTHER tag of the same line, and
  // "Price TBC" on any tag whose id never matched a line id at all (a version
  // view's fixture, PT-202609-0015). `tag_id` is only absent on a row from a
  // backend that predates the combos model, which still has exactly one tag
  // per line, so `line_id` is the correct key for THAT row.
  for (const line of lines) resolvedData[line.tag_id ?? line.line_id] = line;

  const images: Record<string, string> = { ...(body.images ?? {}) };
  for (const line of lines) {
    for (const image of line.images ?? []) {
      if (image.url) images[image.attachment_id] = image.url;
    }
  }

  return {
    page_id: body.page_id ?? '',
    version: body.version ?? 0,
    source: body.source ?? 'version',
    doc: body.doc ?? null,
    resolvedData,
    assets: body.assets ?? {},
    images,
    fonts: body.fonts ?? [],
  };
}

/** How many sheets the payload's document holds. */
export function sheetCountOf(payload: TagSheetDesignPayload | null): number {
  return payload?.doc?.sheets.length ?? 0;
}
