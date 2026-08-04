/**
 * Public catalogue reader.
 *
 * Deliberately NOT `apiFetch`: that resolves a NextAuth token before every
 * call, and a consumer opening a shared link has no session to resolve. A plain
 * relative fetch also keeps this page working for someone who is not, and never
 * will be, a user of the CRM.
 *
 * ---------------------------------------------------------------------------
 * CONTRACT
 *
 * GET /api/v1/public/c/{companyCode}/{slug}
 *     -> { name, slug, doc, collections, tileTemplates, assets }
 *
 * 404 covers all three of "no such company", "no such page" and "not
 * published" - on purpose. An anonymous reader does not get to tell them apart.
 * ---------------------------------------------------------------------------
 */

import type { PageDoc, ResolvedTile, TileField } from '@/lib/dealer-kit/types';

export interface PublishedCatalogue {
  name: string;
  slug: string;
  doc: PageDoc;
  /**
   * Collections resolved SERVER-side for an anonymous reader, so the page never
   * asks for prices of its own and cannot be talked into showing more.
   */
  collections?: Record<string, ResolvedTile[]>;
  tileTemplates?: Record<string, TileField[]>;
  /**
   * The design every collection block uses unless it names one of its own.
   * A seeded brochure names none, so this is the only design it has.
   */
  defaultTileTemplateId?: string | null;
  /**
   * assetId -> signed URL for the section backgrounds this document binds.
   *
   * Signed SERVER-side and strictly: an asset that could not be signed is absent
   * from the map rather than present as a URL the CDN answers 403 to, and the
   * renderer treats absent as "no artwork" - which is a state the design has.
   */
  assets?: Record<string, string>;
}

export class CatalogueNotFoundError extends Error {
  constructor() {
    super('Catalogue not found');
    this.name = 'CatalogueNotFoundError';
  }
}

function apiBase(): string {
  const env = process.env.NEXT_PUBLIC_API_URL;
  return env ? env.replace(/\/$/, '') : '';
}

/**
 * Reads already in flight, keyed by what they are reading.
 *
 * The page commits twice on a cold open - measured, two fetches eleven
 * milliseconds apart from one navigation - so without this the reader downloads
 * the whole brochure twice before seeing any of it. Fixing it here rather than
 * in the effect is deliberate: the second commit is React's business and may
 * come back, and a reader must never pay twice for the same document whatever
 * the render does.
 *
 * The entry is dropped as soon as the read settles. This is a de-duplicator,
 * not a store: what makes a LATER open cheap is the HTTP cache below, which the
 * server drives with an ETag and a max-age.
 */
const inFlight = new Map<string, Promise<PublishedCatalogue>>();

export async function readPublishedCatalogue(
  companyCode: string,
  slug: string,
): Promise<PublishedCatalogue> {
  const key = `${companyCode}/${slug}`;
  const running = inFlight.get(key);
  if (running) return running;

  const read = fetchPublishedCatalogue(companyCode, slug).finally(() => {
    inFlight.delete(key);
  });
  inFlight.set(key, read);
  return read;
}

async function fetchPublishedCatalogue(
  companyCode: string,
  slug: string,
): Promise<PublishedCatalogue> {
  const path = `/api/v1/public/c/${encodeURIComponent(companyCode)}/${encodeURIComponent(slug)}`;
  /*
    No `cache: 'no-store'`. It was there to keep a reader off a stale brochure,
    but it also opted out of revalidation entirely: the server sends an ETag and
    a short max-age, and `no-store` meant a reader who reopened the link paid
    four hundred kilobytes again rather than getting a 304. The default honours
    both, so freshness is now the one number the server sets.
  */
  const response = await fetch(`${apiBase()}${path}`);

  if (response.status === 404) throw new CatalogueNotFoundError();
  if (!response.ok) throw new Error('This catalogue could not be loaded right now.');

  return (await response.json()) as PublishedCatalogue;
}
