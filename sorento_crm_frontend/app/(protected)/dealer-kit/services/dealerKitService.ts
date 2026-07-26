/**
 * Dealer Kit page builder — API client.
 *
 * Wired to the real backend. The contract below is what
 * `app/api/v1/dealer_kit/pages.py` implements; it lives here because the FE is
 * the consumer that breaks when it drifts.
 *
 * ---------------------------------------------------------------------------
 * CONTRACT — all under `/api/v1/dealer-kit`, module-guarded on `dealer_kit`,
 * company-scoped by the ORM filter. Another company's page is a 404, not a 403:
 * "exists but forbidden" would itself leak that it exists.
 * ---------------------------------------------------------------------------
 *
 * GET    /pages                          -> PageSummary[]               page.view
 * POST   /pages           {name, slug}   -> PageDetail  201             page.edit
 * GET    /pages/{id}                     -> PageDetail                  page.view
 *          doc = the `staging` version if one exists, else the newest.
 * DELETE /pages/{id}                     -> 204 (hard, cascades)        page.edit
 *
 * GET    /pages/{id}/versions            -> PageVersion[] newest first  page.view
 * POST   /pages/{id}/versions
 *          {doc, commitMessage}          -> PageVersion 201             page.edit
 *          version = max(version)+1 PER page. Never updates a row.
 *
 * PUT    /pages/{id}/labels/published  {versionId} -> PageVersion       page.publish
 * PUT    /pages/{id}/labels/staging    {versionId} -> PageVersion       page.edit
 *          Publish AND rollback are both the published call, aimed at a version.
 *          Two static routes rather than /labels/{label}: FastAPI resolves
 *          dependencies before path params, so one route could not carry the
 *          right permission declaratively.
 *
 * POST   /pages/{id}/exports {audience,showInvoicePrice,versionId?}
 *          -> 202 {downloadId,status,filename,audience}          page.view
 *          Queues a PDF. 202 because the file does not exist yet - the caller
 *          watches My Downloads. Exporting is READING a catalogue, so it needs
 *          page.view rather than page.edit.
 *
 * Errors use the standard AppException envelope, read with `extractApiError`.
 */

import { apiFetch } from '@/lib/api';
import { extractApiError } from '@/lib/api-client';
import type {
  Page,
  PageDoc,
  PageLabel,
  PageSummary,
  PageVersion,
} from '@/lib/dealer-kit/types';

// The full `/api/v1/...` form, as the SCM services use. The short `/api/<domain>/`
// aliases only work for domains listed in lib/api.ts's rewrite table; an
// unlisted one falls through to Next.js and 404s instead of reaching FastAPI.
const BASE = '/api/v1/dealer-kit';

/** Wire shapes, kept separate from the domain types so a rename on either side is a compile error. */
interface PageSummaryWire {
  id: string;
  name: string;
  slug: string;
  updatedAt: string;
  publishedVersion: number | null;
  latestVersion: number;
  publicPath: string | null;
}

interface PageVersionWire {
  id: string;
  version: number;
  commitMessage: string | null;
  createdBy: string | null;
  createdAt: string;
  labels: PageLabel[];
}

interface PageDetailWire extends PageSummaryWire {
  doc: PageDoc;
  versions: PageVersionWire[];
}

function toVersion(wire: PageVersionWire): PageVersion {
  return {
    id: wire.id,
    version: wire.version,
    commitMessage: wire.commitMessage,
    // The backend resolves this to a person's name. It is never a user id -
    // rendering a UUID in the UI is banned, and "who changed this" is only
    // useful as a name anyway.
    createdBy: wire.createdBy ?? 'Unknown',
    createdAt: wire.createdAt,
    labels: wire.labels ?? [],
  };
}

function toSummary(wire: PageSummaryWire): PageSummary {
  return {
    id: wire.id,
    name: wire.name,
    slug: wire.slug,
    updatedAt: wire.updatedAt,
    publishedVersion: wire.publishedVersion,
    latestVersion: wire.latestVersion,
    publicPath: wire.publicPath ?? null,
  };
}

export async function listPages(): Promise<PageSummary[]> {
  const response = await apiFetch(`${BASE}/pages`);
  if (!response.ok) throw new Error(await extractApiError(response, 'Could not load pages'));

  const rows: PageSummaryWire[] = await response.json();
  return rows.map(toSummary);
}

export async function getPage(pageId: string): Promise<Page> {
  const response = await apiFetch(`${BASE}/pages/${encodeURIComponent(pageId)}`);
  if (!response.ok) throw new Error(await extractApiError(response, 'Could not open this page'));

  const wire: PageDetailWire = await response.json();
  return {
    ...toSummary(wire),
    doc: wire.doc,
    versions: (wire.versions ?? []).map(toVersion),
  };
}

export async function createPage(name: string, slug: string): Promise<Page> {
  const response = await apiFetch(`${BASE}/pages`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name, slug }),
  });
  if (!response.ok) throw new Error(await extractApiError(response, 'Could not create the page'));

  const wire: PageDetailWire = await response.json();
  return { ...toSummary(wire), doc: wire.doc, versions: [] };
}

export async function deletePage(pageId: string): Promise<void> {
  const response = await apiFetch(`${BASE}/pages/${encodeURIComponent(pageId)}`, {
    method: 'DELETE',
  });
  if (!response.ok) throw new Error(await extractApiError(response, 'Could not delete the page'));
}

export async function saveVersion(
  pageId: string,
  doc: PageDoc,
  commitMessage: string,
): Promise<PageVersion> {
  const response = await apiFetch(`${BASE}/pages/${encodeURIComponent(pageId)}/versions`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ doc, commitMessage: commitMessage || null }),
  });
  if (!response.ok) throw new Error(await extractApiError(response, 'Could not save'));

  return toVersion(await response.json());
}

export async function moveLabel(
  pageId: string,
  label: PageLabel,
  versionId: string,
): Promise<PageVersion> {
  const response = await apiFetch(
    `${BASE}/pages/${encodeURIComponent(pageId)}/labels/${label}`,
    {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ versionId }),
    },
  );
  if (!response.ok) {
    throw new Error(
      await extractApiError(
        response,
        label === 'published' ? 'Could not publish' : 'Could not update staging',
      ),
    );
  }

  return toVersion(await response.json());
}


export type ExportAudience = 'staff' | 'dealer' | 'consumer';

export async function requestExport(
  pageId: string,
  audience: ExportAudience = 'staff',
  showInvoicePrice = false,
): Promise<{ downloadId: string; status: string; filename: string | null }> {
  const response = await apiFetch(`${BASE}/pages/${encodeURIComponent(pageId)}/exports`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ audience, showInvoicePrice }),
  });
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Could not start the export'));
  }
  return response.json();
}
