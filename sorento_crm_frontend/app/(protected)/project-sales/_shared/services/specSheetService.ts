import { apiFetch } from '@/lib/api';
import { extractApiError } from '@/lib/api-client';
import type { TagSheetDesignPayload } from '@/lib/dealer-kit/design-payload';
import type {
  TagBindingData,
  TagLayer,
} from '@/lib/dealer-kit/tag-template-types';
import type { QueuedDownload } from './quotationDocumentService';

/**
 * Saved spec sheets of a quotation document (SPEC-SHEET-V2), SS1, SS2 ...
 *
 *   GET   .../quotation-documents/{id}/spec-sheets                         -> SpecSheetList
 *   POST  .../spec-sheets                                                  -> SpecSheetDetail (201)
 *   GET   .../spec-sheets/{sheetId}                                        -> SpecSheetDetail
 *   PATCH .../spec-sheets/{sheetId}                                        -> SpecSheetDetail
 *   GET   .../spec-sheets/{sheetId}/preview?key=a&key=b                       -> one window of pages
 *   GET   .../spec-sheets/{sheetId}/pages/{key}/design                     -> the page designer's input
 *   PUT   .../spec-sheets/{sheetId}/pages/{key}/edit                       -> SpecSheetDetail
 *   POST  .../spec-sheets/{sheetId}/export                                 -> the queued download
 */

const BASE = '/api/v1/project-sales';

export interface SpecSheetRow {
  key: string;
  area: string;
  comment: string;
  marker: string;
  hidden: boolean;
  accessories: string[];
  /** Per-sheet "Spec sheet description" override of the page's item; '' = none. */
  description?: string;
  /** The same for accessories, by product id. */
  accessory_descriptions?: Record<string, string>;
}

export interface SpecSheetAccessory {
  /** Set only on a hand-picked accessory: the item it came from. */
  key: string | null;
  source: 'set' | 'picked';
  product_id: string | null;
  code: string;
  name: string;
  brand: string;
  /** The product's own spec sheet text (field, else description). */
  spec_sheet_description?: string;
}

export type SpecSheetPageTemplate = 'cover' | 'page' | 'single';

export interface SpecSheetPage {
  key: string;
  /** Printed page number (cover is 1); null for a left-out page. */
  number: number | null;
  code: string;
  name: string;
  brand: string;
  /** Typed on the page, else `area_default`. */
  area: string;
  /** The Section heading the line sits under on the Lines tab. */
  area_default: string;
  comment: string;
  marker: string;
  hidden: boolean;
  picked: string[];
  accessories: SpecSheetAccessory[];
  /** The override typed on this sheet ('' = none), and the product text it replaces. */
  description?: string;
  accessory_descriptions?: Record<string, string>;
  spec_sheet_description_default?: string;
  edited: boolean;
  template: SpecSheetPageTemplate;
}

export interface SpecSheetTemplateRef {
  id: string;
  name: string;
  version_no: number;
}

export interface SpecSheetDetail {
  id: string;
  sheet_no: number;
  label: string;
  source_label: string;
  source_hint: string;
  is_draft: boolean;
  templates: {
    cover: SpecSheetTemplateRef | null;
    page: SpecSheetTemplateRef | null;
    single: SpecSheetTemplateRef | null;
  };
  /** Templates the sheet can no longer draw from (deleted before deleting was blocked). */
  templates_missing?: ('cover' | 'page' | 'single')[];
  newer_templates: boolean;
  page_size: { width_mm: number; height_mm: number };
  /** Cover first. No images: the reader asks for those per window. */
  pages: SpecSheetPage[];
  prev_id: string | null;
  next_id: string | null;
  can_edit: boolean;
}

export interface SpecSheetListRow {
  id: string;
  sheet_no: number;
  label: string;
  source_label: string;
  source_hint: string;
  is_draft: boolean;
  cover_name: string;
  page_name: string;
  single_name: string | null;
  page_count: number;
  edited_count: number;
  created_by_name: string;
  created_at: string | null;
  updated_at: string | null;
  last_exported_at: string | null;
  newer_templates: boolean;
}

export interface SpecSheetSource {
  value: string;
  label: string;
  hint: string;
}

export interface SpecSheetTemplateOption {
  id: string;
  name: string;
  width_mm: number | null;
  height_mm: number | null;
}

export interface SpecSheetList {
  items: SpecSheetListRow[];
  sources: SpecSheetSource[];
  templates: {
    cover: SpecSheetTemplateOption[];
    page: SpecSheetTemplateOption[];
  };
  defaults: {
    source: string | null;
    cover_template_id: string | null;
    page_template_id: string | null;
    single_page_template_id: string | null;
  };
  create_disabled_reason: string | null;
}

export interface CreateSpecSheetBody {
  source: string;
  cover_template_id: string;
  page_template_id: string;
  single_page_template_id: string | null;
}

export interface UpdateSpecSheetBody {
  rows?: SpecSheetRow[];
  use_latest_templates?: boolean;
  /** Pick the templates again; the rows and page edits stay. */
  cover_template_id?: string;
  page_template_id?: string;
  single_page_template_id?: string | null;
}

/** One window of the print payload, thumbnails only, plus the pages the sheet leaves out. */
export type SpecSheetPreview = Omit<
  TagSheetDesignPayload,
  'page_id' | 'source'
> & {
  page_size: { width_mm: number; height_mm: number };
  hidden: string[];
};

export interface SpecSheetPageDesign {
  layers: TagLayer[];
  /** The page's resolved row, in the shape the designer binds a line to. */
  bound: Extract<TagBindingData, { kind: 'line' }>['line'];
  images: Record<string, string>;
  assets: Record<string, string>;
  fonts: TagSheetDesignPayload['fonts'];
  width_mm: number;
  height_mm: number;
  template_name: string;
  template_id: string | null;
  edited: boolean;
}

function url(projectId: string, documentId: string, suffix = '') {
  return `${BASE}/projects/${projectId}/quotation-documents/${documentId}/spec-sheets${suffix}`;
}

const JSON_HEADERS = { 'Content-Type': 'application/json' };

async function read<T>(response: Response, fallback: string): Promise<T> {
  if (!response.ok) throw new Error(await extractApiError(response, fallback));
  return response.json();
}

export async function listSpecSheets(
  projectId: string,
  documentId: string,
): Promise<SpecSheetList> {
  return read(
    await apiFetch(url(projectId, documentId)),
    'Could not load the spec sheets',
  );
}

export async function createSpecSheet(
  projectId: string,
  documentId: string,
  body: CreateSpecSheetBody,
): Promise<SpecSheetDetail> {
  return read(
    await apiFetch(url(projectId, documentId), {
      method: 'POST',
      headers: JSON_HEADERS,
      body: JSON.stringify(body),
    }),
    'Could not create the spec sheet',
  );
}

export async function getSpecSheet(
  projectId: string,
  documentId: string,
  sheetId: string,
): Promise<SpecSheetDetail> {
  return read(
    await apiFetch(url(projectId, documentId, `/${sheetId}`)),
    'Could not load the spec sheet',
  );
}

export async function updateSpecSheet(
  projectId: string,
  documentId: string,
  sheetId: string,
  body: UpdateSpecSheetBody,
): Promise<SpecSheetDetail> {
  return read(
    await apiFetch(url(projectId, documentId, `/${sheetId}`), {
      method: 'PATCH',
      headers: JSON_HEADERS,
      body: JSON.stringify(body),
    }),
    'Could not save the spec sheet',
  );
}

export async function getSpecSheetPreview(
  projectId: string,
  documentId: string,
  sheetId: string,
  keys: string[],
): Promise<SpecSheetPreview> {
  // One `key` per page: a key may itself hold a slash or a comma (a `code:AB/12` item).
  const query = `?${keys.map((key) => `key=${encodeURIComponent(key)}`).join('&')}`;
  return read(
    await apiFetch(url(projectId, documentId, `/${sheetId}/preview${query}`)),
    'Could not draw the spec sheet pages',
  );
}

export async function getSpecSheetPageDesign(
  projectId: string,
  documentId: string,
  sheetId: string,
  key: string,
): Promise<SpecSheetPageDesign> {
  return read(
    await apiFetch(
      url(
        projectId,
        documentId,
        `/${sheetId}/pages/${encodeURIComponent(key)}/design`,
      ),
    ),
    'Could not open the page',
  );
}

export async function saveSpecSheetPageEdit(
  projectId: string,
  documentId: string,
  sheetId: string,
  key: string,
  layers: TagLayer[],
): Promise<SpecSheetDetail> {
  return read(
    await apiFetch(
      url(
        projectId,
        documentId,
        `/${sheetId}/pages/${encodeURIComponent(key)}/edit`,
      ),
      {
        method: 'PUT',
        headers: JSON_HEADERS,
        body: JSON.stringify({ layers }),
      },
    ),
    'Could not save the page',
  );
}

/** The open page's pictures and library artwork at a sharper rendition than the thumbnails. */
export interface SpecSheetPageImages {
  /** attachment id -> url */
  images: Record<string, string>;
  /** asset id -> url */
  assets: Record<string, string>;
}

export async function getSpecSheetPageImages(
  projectId: string,
  documentId: string,
  sheetId: string,
  key: string,
): Promise<SpecSheetPageImages> {
  return read(
    await apiFetch(
      url(
        projectId,
        documentId,
        `/${sheetId}/page-images?key=${encodeURIComponent(key)}`,
      ),
    ),
    'Failed to load the page',
  );
}

/** Layer keys "Apply to every page" may carry: where it sits and how it is styled, never its content. */
export interface ApplyAllChanges {
  x_mm?: number;
  y_mm?: number;
  width_mm?: number;
  height_mm?: number;
  rotation_deg?: number;
  z_index?: number;
  visible?: boolean;
  props?: Record<string, string | number | boolean>;
}

/** Move or restyle one layer on every page of the sheet that has it. */
export async function applySpecSheetLayerToAll(
  projectId: string,
  documentId: string,
  sheetId: string,
  layerId: string,
  changes: ApplyAllChanges,
  originPageKey?: string,
): Promise<SpecSheetDetail> {
  return read(
    await apiFetch(
      url(
        projectId,
        documentId,
        `/${sheetId}/layers/${encodeURIComponent(layerId)}/apply-all`,
      ),
      {
        method: 'POST',
        headers: JSON_HEADERS,
        body: JSON.stringify({ changes, origin_page_key: originPageKey }),
      },
    ),
    'Could not apply the change to every page',
  );
}

export async function queueSpecSheetPdf(
  projectId: string,
  documentId: string,
  sheetId: string,
): Promise<QueuedDownload> {
  return read(
    await apiFetch(url(projectId, documentId, `/${sheetId}/export`), {
      method: 'POST',
    }),
    'Could not queue the spec sheet',
  );
}
